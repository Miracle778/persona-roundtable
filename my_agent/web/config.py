from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any


APP_CONFIG_DIR = Path.home() / ".config" / "my_agent"
DEFAULT_CONFIG_PATH = APP_CONFIG_DIR / "config.json"

DEFAULT_PROVIDER_TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "openai",
        "name": "OpenAI",
        "kind": "openai-compatible",
        "base_url": "https://api.openai.com/v1",
        "api_key": "",
        "available_models": ["gpt-4o", "gpt-4o-mini"],
        "default_model": "gpt-4o-mini",
        "enabled": True,
    },
    {
        "id": "volces-coding",
        "name": "火山方舟 Coding Plan",
        "kind": "openai-compatible",
        "base_url": "https://ark.cn-beijing.volces.com/api/coding/v3",
        "api_key": "",
        "available_models": ["minimax-m2.7", "deepseek-v3.2", "glm-5.1"],
        "default_model": "minimax-m2.7",
        "enabled": True,
    },
]


def default_config() -> dict[str, Any]:
    return {
        "version": 1,
        "default_model": {
            "provider_id": "volces-coding",
            "model": "minimax-m2.7",
        },
        "providers": deepcopy(DEFAULT_PROVIDER_TEMPLATES),
    }


def ensure_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or default_config_path()
    if config_path.exists():
        return load_config(config_path)
    config = default_config()
    save_config(config, config_path)
    return config


def load_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or default_config_path()
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ensure_config(config_path)
    except json.JSONDecodeError as exc:
        raise ValueError(f"配置文件不是合法 JSON：{config_path}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"配置文件根节点必须是对象：{config_path}")
    data.setdefault("version", 1)
    data.setdefault("providers", [])
    data.setdefault("default_model", {})
    return data


def save_config(config: dict[str, Any], path: Path | None = None) -> Path:
    config_path = path or default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if os.name != "nt":
        os.chmod(config_path, 0o600)
    return config_path


def default_config_path() -> Path:
    override = os.environ.get("MY_AGENT_CONFIG_PATH", "").strip()
    return Path(override).expanduser() if override else DEFAULT_CONFIG_PATH


def masked_config(config: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(config)
    for provider in result.get("providers") or []:
        if isinstance(provider, dict):
            provider["api_key"] = mask_secret(str(provider.get("api_key") or ""))
            provider["has_api_key"] = bool(config_provider_by_id(config, provider.get("id")).get("api_key"))
    return result


def config_provider_by_id(config: dict[str, Any], provider_id: object) -> dict[str, Any]:
    for provider in config.get("providers") or []:
        if isinstance(provider, dict) and provider.get("id") == provider_id:
            return provider
    return {}


def mask_secret(secret: str) -> str:
    if not secret:
        return ""
    if len(secret) <= 8:
        return "*" * len(secret)
    prefix = secret[:3]
    suffix = secret[-4:]
    return f"{prefix}{'*' * 10}{suffix}"
