from __future__ import annotations

import time
from contextlib import contextmanager
from pathlib import Path
from collections.abc import Iterator
from typing import Any, Iterable

from my_agent.core.llm import OpenAICompatibleClient
from my_agent.core.skill_loader import load_skills
from my_agent.web.config import (
    ensure_config,
    default_config_path,
    load_config,
    mask_secret,
    masked_config,
    save_config,
)
from my_agent.web.db import (
    add_session_personas as db_add_session_personas,
    archive_persona as db_archive_persona,
    assign_persona_model as db_assign_persona_model,
    clone_persona as db_clone_persona,
    connect,
    default_db_path,
    create_session as db_create_session,
    ensure_schema,
    get_persona,
    get_session,
    import_skills_as_personas,
    list_personas as db_list_personas,
    list_sessions as db_list_sessions,
    record_message,
    search_sessions,
    update_persona as db_update_persona,
)
from my_agent.web.topic import TopicCard, refine_topic


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SKILL_DIRS = [PACKAGE_ROOT / "demo_skills", PACKAGE_ROOT / "skills"]


class WebAppService:
    def __init__(
        self,
        db_path: Path | str | None = None,
        config_path: Path | None = None,
        skill_dirs: Iterable[Path] | None = None,
        topic_llm_client: Any | None = None,
        provider_test_client_factory: Any | None = None,
    ):
        self.db_path = Path(db_path) if db_path is not None else default_db_path()
        self.config_path = config_path or default_config_path()
        self.skill_dirs = list(skill_dirs or DEFAULT_SKILL_DIRS)
        self.topic_llm_client = topic_llm_client
        self.provider_test_client_factory = provider_test_client_factory

    def bootstrap(self) -> None:
        ensure_config(self.config_path)
        with self.connection() as conn:
            ensure_schema(conn)
            if not db_list_personas(conn):
                import_skills_as_personas(conn, load_skills(self.skill_dirs))

    @contextmanager
    def connection(self):
        conn = connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def get_config(self, masked: bool = True) -> dict[str, Any]:
        config = ensure_config(self.config_path)
        return masked_config(config) if masked else config

    def update_config(self, config: dict[str, Any]) -> dict[str, Any]:
        config = merge_masked_provider_api_keys(
            incoming=config,
            current=self.get_config(masked=False),
        )
        save_config(config, self.config_path)
        return self.get_config(masked=True)

    def test_provider_connection(self, provider_id: str, model: str | None = None) -> dict[str, Any]:
        config = self.get_config(masked=False)
        provider = provider_by_id(config, provider_id)
        if not provider:
            raise ValueError(f"找不到 Provider：{provider_id}")
        selected_model = (
            model
            or provider.get("default_model")
            or (provider.get("available_models") or [None])[0]
        )
        api_key = str(provider.get("api_key") or "")
        base_url = str(provider.get("base_url") or "")
        if not base_url:
            return {
                "ok": False,
                "provider_id": provider_id,
                "model": selected_model,
                "error": "Provider 缺少 base_url。",
            }
        if not api_key:
            return {
                "ok": False,
                "provider_id": provider_id,
                "model": selected_model,
                "error": "Provider 缺少 API Key。",
            }
        if not selected_model:
            return {
                "ok": False,
                "provider_id": provider_id,
                "model": selected_model,
                "error": "Provider 缺少可测试模型。",
            }
        factory = self.provider_test_client_factory or OpenAICompatibleClient
        try:
            client = factory(
                model=str(selected_model),
                base_url=base_url,
                api_key=api_key,
                timeout=15,
            )
            message = client.complete("请用一句中文回复：连接测试成功。").strip()
        except Exception as exc:
            return {
                "ok": False,
                "provider_id": provider_id,
                "model": selected_model,
                "error": str(exc),
            }
        return {
            "ok": True,
            "provider_id": provider_id,
            "model": selected_model,
            "message": message[:240],
        }

    def list_personas(self) -> list[dict[str, Any]]:
        with self.connection() as conn:
            return db_list_personas(conn)

    def clone_persona(
        self,
        source_persona_id: str,
        display_name: str | None = None,
    ) -> dict[str, Any]:
        with self.connection() as conn:
            clone_id = db_clone_persona(
                conn,
                source_persona_id=source_persona_id,
                display_name=display_name,
            )
            persona = get_persona(conn, clone_id)
        if not persona:
            raise RuntimeError(f"读取角色副本失败：{clone_id}")
        return persona

    def update_persona(self, persona_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        categories = updates.get("categories")
        if categories is not None:
            categories = [str(item).strip() for item in categories if str(item).strip()]
        with self.connection() as conn:
            changed = db_update_persona(
                conn,
                persona_id,
                display_name=string_or_none(updates.get("display_name")),
                description=string_or_none(updates.get("description")),
                categories=categories,
                prompt=string_or_none(updates.get("prompt")),
            )
            if not changed:
                raise ValueError(f"找不到可编辑的角色：{persona_id}")
            persona = get_persona(conn, persona_id)
        if not persona:
            raise RuntimeError(f"读取角色失败：{persona_id}")
        return persona

    def archive_persona(self, persona_id: str) -> dict[str, Any]:
        with self.connection() as conn:
            changed = db_archive_persona(conn, persona_id)
        if not changed:
            raise ValueError(f"找不到可归档的角色：{persona_id}")
        return {"archived": True, "id": persona_id}

    def assign_persona_model(
        self,
        persona_ids: list[str],
        provider_id: str | None,
        model: str | None,
    ) -> dict[str, Any]:
        with self.connection() as conn:
            changed = db_assign_persona_model(
                conn,
                persona_ids=persona_ids,
                provider_id=provider_id,
                model=model,
                model_source="explicit" if provider_id and model else "inherit",
            )
        return {"updated": changed}

    def list_sessions(self, query: str | None = None) -> list[dict[str, Any]]:
        with self.connection() as conn:
            if query:
                return search_sessions(conn, query)
            return db_list_sessions(conn)

    def refine_topic(
        self,
        raw_input: str,
        title: str | None = None,
        clarification_answers: list[str] | None = None,
        previous_topic: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return refine_topic(
            raw_input,
            title=title,
            clarification_answers=clarification_answers,
            previous_topic=previous_topic,
            llm_client=self.topic_llm_client or self.build_topic_llm_client(),
        ).to_dict()

    def create_session(
        self,
        raw_input: str,
        topic: dict[str, Any] | TopicCard,
        persona_ids: list[str],
        style: str = "analysis",
    ) -> dict[str, Any]:
        topic_card = topic if isinstance(topic, TopicCard) else topic_from_dict(topic)
        provider_id, model = self.default_model()
        with self.connection() as conn:
            session_id = db_create_session(
                conn,
                raw_input=raw_input,
                topic=topic_card,
                persona_ids=persona_ids,
                style=style,
                default_provider_id=provider_id,
                default_model=model,
            )
            record_message(
                conn,
                session_id=session_id,
                role="user",
                speaker="你",
                content=raw_input,
                provider_id=provider_id,
                model=model,
            )
            session = get_session(conn, session_id)
        if not session:
            raise RuntimeError(f"创建会话失败：{session_id}")
        return session

    def add_session_personas(self, session_id: str, persona_ids: list[str]) -> dict[str, Any]:
        with self.connection() as conn:
            changed = db_add_session_personas(conn, session_id, persona_ids)
            if changed is None:
                raise ValueError(f"找不到会话：{session_id}")
            session = get_session(conn, session_id)
        if not session:
            raise RuntimeError(f"读取会话失败：{session_id}")
        return session

    def continue_session(self, session_id: str, user_message: str) -> dict[str, Any]:
        updated: dict[str, Any] | None = None
        for event in self.continue_session_events(session_id, user_message):
            if event["type"] == "done":
                updated = event["session"]
        if not updated:
            raise RuntimeError(f"读取会话失败：{session_id}")
        return updated

    def continue_session_events(
        self,
        session_id: str,
        user_message: str,
    ) -> Iterator[dict[str, Any]]:
        provider_id, model = self.default_model()
        config = self.get_config(masked=False)
        with self.connection() as conn:
            session = get_session(conn, session_id)
            if not session:
                raise ValueError(f"找不到会话：{session_id}")
            record_message(
                conn,
                session_id=session_id,
                role="user",
                speaker="你",
                content=user_message,
                provider_id=provider_id,
                model=model,
            )
            yield {
                "type": "message",
                "message": {
                    "role": "user",
                    "speaker": "你",
                    "content": user_message,
                    "provider_id": provider_id,
                    "model": model,
                },
            }
            personas = session.get("personas") or []
            round_index = next_round_index(session.get("messages") or [])
            for persona in personas:
                actual_provider = persona.get("provider_id_snapshot") or provider_id
                actual_model = persona.get("model_snapshot") or model
                started_at = time.monotonic()
                reply, error = build_persona_reply(
                    config=config,
                    provider_id=actual_provider,
                    model=actual_model,
                    persona_name=persona["display_name_snapshot"],
                    persona_prompt=persona.get("prompt_snapshot") or "",
                    topic=session["refined_topic"],
                    task=session.get("discussion_task") or "",
                    user_message=user_message,
                )
                latency_ms = int((time.monotonic() - started_at) * 1000)
                record_message(
                    conn,
                    session_id=session_id,
                    role="persona",
                    speaker=persona["display_name_snapshot"],
                    content=reply,
                    persona_id=persona["persona_id"],
                    round_index=round_index,
                    provider_id=actual_provider,
                    model=actual_model,
                    total_tokens=0,
                    latency_ms=latency_ms,
                    error=error,
                )
                yield {
                    "type": "message",
                    "message": {
                        "role": "persona",
                        "speaker": persona["display_name_snapshot"],
                        "content": reply,
                        "persona_id": persona["persona_id"],
                        "round_index": round_index,
                        "provider_id": actual_provider,
                        "model": actual_model,
                        "total_tokens": 0,
                        "latency_ms": latency_ms,
                        "error": error,
                    },
                }
            updated = get_session(conn, session_id)
            if not updated:
                raise RuntimeError(f"读取会话失败：{session_id}")
            yield {"type": "done", "session": updated}

    def default_model(self) -> tuple[str | None, str | None]:
        config = load_config(self.config_path)
        default = config.get("default_model") or {}
        return default.get("provider_id"), default.get("model")

    def build_topic_llm_client(self) -> OpenAICompatibleClient | None:
        config = self.get_config(masked=False)
        provider_id, model = self.default_model()
        provider = provider_by_id(config, provider_id)
        api_key = str(provider.get("api_key") or "")
        base_url = str(provider.get("base_url") or "")
        if not api_key or not base_url or not model:
            return None
        return OpenAICompatibleClient(model=model, base_url=base_url, api_key=api_key)


def topic_from_dict(data: dict[str, Any]) -> TopicCard:
    return TopicCard(
        title=str(data.get("title") or "未命名讨论"),
        tags=[str(item) for item in data.get("tags") or []],
        discussion_task=str(data.get("discussion_task") or ""),
        source_summary=str(data.get("source_summary") or ""),
        suggested_agent_ids=[str(item) for item in data.get("suggested_agent_ids") or []],
        clarification_round_limit=int(data.get("clarification_round_limit") or 3),
        clarification_questions=[str(item) for item in data.get("clarification_questions") or []],
        clarification_round=int(data.get("clarification_round") or 0),
        refinement_source=str(data.get("refinement_source") or "local"),
        fallback_reason=data.get("fallback_reason"),
    )


def merge_masked_provider_api_keys(
    incoming: dict[str, Any],
    current: dict[str, Any],
) -> dict[str, Any]:
    current_providers = {
        provider.get("id"): provider
        for provider in current.get("providers") or []
        if isinstance(provider, dict)
    }
    merged = dict(incoming)
    providers: list[Any] = []
    for provider in incoming.get("providers") or []:
        if not isinstance(provider, dict):
            providers.append(provider)
            continue
        next_provider = dict(provider)
        current_provider = current_providers.get(next_provider.get("id")) or {}
        current_key = str(current_provider.get("api_key") or "")
        incoming_key = str(next_provider.get("api_key") or "")
        if current_key and incoming_key == mask_secret(current_key):
            next_provider["api_key"] = current_key
        providers.append(next_provider)
    merged["providers"] = providers
    return merged


def string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def next_round_index(messages: list[dict[str, Any]]) -> int:
    current = 0
    for item in messages:
        try:
            current = max(current, int(item.get("round_index") or 0))
        except (TypeError, ValueError):
            continue
    return current + 1


def build_mock_persona_reply(persona_name: str, topic: str, user_message: str) -> str:
    focus = user_message.strip() or topic
    return (
        f"从「{persona_name}」的角度看，本轮可以先围绕「{topic}」继续收束。"
        f"你刚才提到「{focus}」，关键不是把观点说满，而是先验证事实、成本和商业化路径，"
        "再决定下一步投入。"
    )


def build_persona_reply(
    config: dict[str, Any],
    provider_id: str | None,
    model: str | None,
    persona_name: str,
    persona_prompt: str,
    topic: str,
    task: str,
    user_message: str,
) -> tuple[str, str | None]:
    provider = provider_by_id(config, provider_id)
    api_key = str(provider.get("api_key") or "")
    base_url = str(provider.get("base_url") or "")
    if not api_key or not base_url or not model:
        return build_mock_persona_reply(persona_name, topic, user_message), None
    prompt = build_persona_prompt(
        persona_name=persona_name,
        persona_prompt=persona_prompt,
        topic=topic,
        task=task,
        user_message=user_message,
    )
    try:
        client = OpenAICompatibleClient(model=model, base_url=base_url, api_key=api_key)
        return client.complete(prompt).strip(), None
    except Exception as exc:
        fallback = build_mock_persona_reply(persona_name, topic, user_message)
        return f"模型调用失败，已用本地草稿继续。\n\n{fallback}", str(exc)


def provider_by_id(config: dict[str, Any], provider_id: str | None) -> dict[str, Any]:
    for provider in config.get("providers") or []:
        if isinstance(provider, dict) and provider.get("id") == provider_id:
            return provider
    return {}


def build_persona_prompt(
    persona_name: str,
    persona_prompt: str,
    topic: str,
    task: str,
    user_message: str,
) -> str:
    return f"""
你是多角色讨论工作台中的一个角色代理，不要声称自己是真实人物。

角色名称：
{persona_name}

角色设定：
{persona_prompt[:4000]}

本次精炼主题：
{topic}

讨论任务：
{task}

用户刚才补充：
{user_message}

请输出一段中文发言，80-220 字。直接回应用户补充，围绕精炼主题推进讨论，不要列无关清单。
""".strip()
