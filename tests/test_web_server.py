from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

import httpx

from my_agent.web.server import create_app
from my_agent.web.service import WebAppService


class FakeTopicLLM:
    def __init__(self):
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return json.dumps(
            {
                "title": "HTTP 精炼主题",
                "tags": ["创业产品"],
                "discussion_task": "通过 HTTP 精炼后的讨论任务。",
                "source_summary": "HTTP topic refine smoke。",
                "clarification_questions": [],
            },
            ensure_ascii=False,
        )


class FakeProviderClient:
    def complete(self, prompt: str) -> str:
        return "HTTP provider connection ok"


class WebServerTests(unittest.TestCase):
    def test_api_refine_personas_and_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_dir = root / "skills" / "test-skill"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                """---
name: test-perspective
description: 测试角色
categories:
  - 创业产品
---

# 测试角色

## 角色扮演规则

保持清晰。
""",
                encoding="utf-8",
            )
            service = WebAppService(
                db_path=root / "web.sqlite",
                config_path=root / "config.json",
                skill_dirs=[root / "skills"],
                topic_llm_client=FakeTopicLLM(),
                provider_test_client_factory=lambda **kwargs: FakeProviderClient(),
            )
            service.bootstrap()
            app = create_app(service=service, static_dir=root)
            asyncio.run(self._exercise_api(app))

    async def _exercise_api(self, app) -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            topic = await post_json(
                client,
                "/api/topic/refine",
                {"raw_input": "AI 产品怎么做"},
            )
            self.assertIn("title", topic)
            clarified = await post_json(
                client,
                "/api/topic/refine",
                {
                    "raw_input": "AI 产品怎么做",
                    "previous_topic": topic,
                    "clarification_answers": ["更关心 B 端付费验证"],
                },
            )
            self.assertEqual(clarified["title"], "HTTP 精炼主题")
            self.assertEqual(clarified["clarification_round"], 1)
            self.assertEqual(clarified["refinement_source"], "llm")

            config = await get_json(client, "/api/config")
            config["providers"][0]["api_key"] = "sk-test"
            config = await post_json(client, "/api/config", config)
            provider = config["providers"][0]
            provider_test = await post_json(
                client,
                "/api/providers/test",
                {
                    "provider_id": provider["id"],
                    "model": provider["available_models"][0],
                },
            )
            self.assertTrue(provider_test["ok"])
            self.assertEqual(provider_test["message"], "HTTP provider connection ok")

            personas = await get_json(client, "/api/personas")
            persona_id = personas[0]["id"]
            clone = await post_json(
                client,
                "/api/personas",
                {"source_persona_id": persona_id, "display_name": "测试角色副本"},
                expected_status=201,
            )
            self.assertNotEqual(clone["id"], persona_id)
            patched = await request_json(
                client,
                "PATCH",
                f"/api/personas/{clone['id']}",
                {
                    "display_name": "商业化测试角色",
                    "description": "专注商业化验证",
                    "categories": ["创业产品", "投资市场"],
                    "prompt": "只编辑 persona 副本，不修改原始 Skill。",
                    "provider_id": "openai",
                    "model": "gpt-4o-mini",
                },
            )
            self.assertEqual(patched["display_name"], "商业化测试角色")
            self.assertIn("persona 副本", patched["prompt"])
            self.assertEqual(patched["provider_id"], "openai")
            self.assertEqual(patched["model"], "gpt-4o-mini")

            created_persona = await post_json(
                client,
                "/api/personas",
                {"display_name": "自定义角色"},
                expected_status=201,
            )
            self.assertTrue(created_persona["id"].startswith("persona-"))
            self.assertIsNone(created_persona["source_skill_id"])
            self.assertEqual(created_persona["display_name"], "自定义角色")

            session = await post_json(
                client,
                "/api/sessions",
                {
                    "raw_input": "AI 产品怎么做",
                    "topic": topic,
                    "persona_ids": [persona_id],
                },
                expected_status=201,
            )
            self.assertEqual(session["messages"][0]["role"], "user")
            self.assertEqual(len(session["personas"]), 1)

            expanded_session = await post_json(
                client,
                f"/api/sessions/{session['id']}/personas",
                {"persona_ids": [clone["id"]]},
            )
            self.assertEqual(len(expanded_session["personas"]), 2)
            self.assertIn(
                "商业化测试角色",
                [item["display_name_snapshot"] for item in expanded_session["personas"]],
            )

            updated = await post_json(
                client,
                f"/api/sessions/{session['id']}/messages",
                {"content": "继续说商业化"},
                expected_status=201,
            )
            self.assertGreaterEqual(len(updated["messages"]), 3)

            stream_text = await stream_text_response(
                client,
                f"/api/sessions/{session['id']}/stream",
                {"content": "再补充一轮流式观点"},
            )
            self.assertIn("event: message", stream_text)
            self.assertIn("event: done", stream_text)
            self.assertIn("再补充一轮流式观点", stream_text)

            streamed_session = await get_json(client, f"/api/sessions/{session['id']}")
            streamed_persona_messages = [
                item for item in streamed_session["messages"] if item["role"] == "persona"
            ]
            self.assertGreaterEqual(len(streamed_persona_messages), 2)

            deleted = await request_json(client, "DELETE", f"/api/personas/{clone['id']}")
            self.assertTrue(deleted["archived"])


async def get_json(client: httpx.AsyncClient, path: str):
    response = await client.get(path)
    response.raise_for_status()
    return response.json()


async def post_json(
    client: httpx.AsyncClient,
    path: str,
    payload: dict,
    expected_status: int = 200,
):
    return await request_json(client, "POST", path, payload, expected_status=expected_status)


async def request_json(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    payload: dict | None = None,
    expected_status: int = 200,
):
    response = await client.request(method, path, json=payload)
    if response.status_code != expected_status:
        raise AssertionError(
            f"{method} {path} returned {response.status_code}: {response.text}"
        )
    return response.json()


async def stream_text_response(
    client: httpx.AsyncClient,
    path: str,
    payload: dict,
    expected_status: int = 200,
) -> str:
    async with client.stream("POST", path, json=payload) as response:
        if response.status_code != expected_status:
            text = await response.aread()
            raise AssertionError(
                f"POST {path} returned {response.status_code}: {text.decode()}"
            )
        content_type = response.headers.get("content-type", "")
        if "text/event-stream" not in content_type:
            raise AssertionError(f"expected SSE content-type, got {content_type}")
        return (await response.aread()).decode()


if __name__ == "__main__":
    unittest.main()
