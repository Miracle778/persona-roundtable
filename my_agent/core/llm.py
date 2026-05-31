from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from shlex import quote
from typing import Any


class LLMClient(ABC):
    @abstractmethod
    def complete(self, prompt: str) -> str:
        """Return model text for a prompt."""


class MockLLMClient(LLMClient):
    def complete(self, prompt: str) -> str:
        marker = "请输出一段讨论发言。"
        if marker in prompt:
            return ""
        return "这是 mock 输出。"


class LLMConfigError(RuntimeError):
    """Raised when an LLM backend is not configured correctly."""


class LLMRequestError(RuntimeError):
    """Raised when an LLM request fails."""


@dataclass(frozen=True)
class OpenCodeLLMConfig:
    provider_id: str
    model: str
    base_url: str
    api_key: str
    available_models: list[str]


class OpenAICompatibleClient(LLMClient):
    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: str,
        timeout: int = 60,
        temperature: float = 0.7,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.temperature = temperature

    def complete(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw_body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise LLMRequestError(
                f"LLM 请求失败：HTTP {exc.code}。返回内容：{body[:500]}"
            ) from exc
        except urllib.error.URLError as exc:
            raise LLMRequestError(
                f"LLM 请求失败：无法连接到 {self.base_url}。原因：{exc.reason}"
            ) from exc
        except TimeoutError as exc:
            raise LLMRequestError(f"LLM 请求超时：超过 {self.timeout} 秒。") from exc

        try:
            result = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise LLMRequestError(
                f"LLM 返回不是合法 JSON：{raw_body[:500]}"
            ) from exc

        try:
            content = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMRequestError(
                "LLM 返回结构不是 OpenAI-compatible chat/completions 格式。"
                f"返回内容：{json.dumps(result, ensure_ascii=False)[:500]}"
            ) from exc
        if not isinstance(content, str) or not content.strip():
            raise LLMRequestError("LLM 返回了空内容。")
        return content


def load_dotenv_files(paths: list[Path]) -> list[Path]:
    loaded: list[Path] = []
    for path in paths:
        if not path.exists():
            continue
        load_dotenv_file(path)
        loaded.append(path)
    return loaded


def load_dotenv_file(path: Path) -> None:
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            raise LLMConfigError(f"{path}:{line_number} 不是合法的 KEY=VALUE 格式。")
        key, value = line.split("=", 1)
        key = key.strip()
        value = parse_dotenv_value(value.strip())
        if not key:
            raise LLMConfigError(f"{path}:{line_number} 缺少环境变量名。")
        os.environ.setdefault(key, value)


def parse_dotenv_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    if value.startswith('"'):
        return bytes(value, "utf-8").decode("unicode_escape")
    return value


def build_llm(mode: str = "mock", model_override: str | None = None) -> LLMClient:
    if mode == "openai":
        api_key = os.environ.get("MY_AGENT_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise LLMConfigError(
                "缺少 LLM API Key。请先运行：\n"
                "  python3 -m my_agent llm-env-from-opencode --show-secret\n"
                "然后把输出的 export 命令复制到当前 shell；或手动设置 MY_AGENT_API_KEY。"
            )
        model = model_override or os.environ.get("MY_AGENT_MODEL", "gpt-4.1-mini")
        base_url = os.environ.get("MY_AGENT_BASE_URL", "https://api.openai.com/v1")
        temperature = read_float_env("MY_AGENT_TEMPERATURE", 0.7)
        timeout = read_int_env("MY_AGENT_TIMEOUT", 60)
        return OpenAICompatibleClient(
            model=model,
            base_url=base_url,
            api_key=api_key,
            temperature=temperature,
            timeout=timeout,
        )
    return MockLLMClient()


def read_float_env(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise LLMConfigError(f"{name} 必须是数字，当前值：{value}") from exc


def read_int_env(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise LLMConfigError(f"{name} 必须是整数，当前值：{value}") from exc


def parse_available_models(value: str | None = None) -> list[str]:
    raw = value if value is not None else os.environ.get("MY_AGENT_AVAILABLE_MODELS", "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def load_opencode_llm_config(path: Path | None = None) -> OpenCodeLLMConfig:
    config_path = path or Path.home() / ".config" / "opencode" / "opencode.json"
    try:
        raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LLMConfigError(f"找不到 opencode 配置文件：{config_path}") from exc
    except json.JSONDecodeError as exc:
        raise LLMConfigError(f"opencode 配置不是合法 JSON：{config_path}") from exc

    model_ref = raw_config.get("model")
    if not isinstance(model_ref, str) or "/" not in model_ref:
        raise LLMConfigError("opencode 配置中的 model 应为 provider/model 格式。")
    provider_id, model = model_ref.split("/", 1)
    providers = raw_config.get("provider")
    if not isinstance(providers, dict) or provider_id not in providers:
        raise LLMConfigError(f"opencode 配置里找不到 provider：{provider_id}")

    provider = providers[provider_id]
    options = provider.get("options", {}) if isinstance(provider, dict) else {}
    if not isinstance(options, dict):
        raise LLMConfigError(f"provider {provider_id} 的 options 格式不正确。")
    base_url = options.get("baseURL") or options.get("baseUrl") or options.get("base_url")
    api_key = options.get("apiKey") or options.get("api_key")
    if not isinstance(base_url, str) or not base_url:
        raise LLMConfigError(f"provider {provider_id} 缺少 baseURL。")
    if not isinstance(api_key, str) or not api_key:
        raise LLMConfigError(f"provider {provider_id} 缺少 apiKey。")

    models = provider.get("models", {}) if isinstance(provider, dict) else {}
    available_models = list(models.keys()) if isinstance(models, dict) else []
    if model not in available_models:
        available_models.insert(0, model)

    return OpenCodeLLMConfig(
        provider_id=provider_id,
        model=model,
        base_url=base_url,
        api_key=api_key,
        available_models=available_models,
    )


def render_env_exports_from_opencode(
    config: OpenCodeLLMConfig,
    show_secret: bool = False,
) -> str:
    api_key = config.api_key if show_secret else "***"
    exports: dict[str, str] = {
        "MY_AGENT_BASE_URL": config.base_url,
        "MY_AGENT_API_KEY": api_key,
        "MY_AGENT_MODEL": config.model,
        "MY_AGENT_AVAILABLE_MODELS": ",".join(config.available_models),
    }
    return "\n".join(f"export {key}={quote(value)}" for key, value in exports.items())


def llm_models_from_environment_or_opencode() -> tuple[str | None, list[str], str]:
    env_models = parse_available_models()
    env_model = os.environ.get("MY_AGENT_MODEL")
    if env_models or env_model:
        models = env_models or ([env_model] if env_model else [])
        return env_model, models, "env"

    config = load_opencode_llm_config()
    return config.model, config.available_models, "opencode"


def as_error_message(exc: Exception) -> str:
    if isinstance(exc, (LLMConfigError, LLMRequestError)):
        return str(exc)
    if isinstance(exc, RuntimeError):
        return str(exc)
    return f"{type(exc).__name__}: {exc}"
