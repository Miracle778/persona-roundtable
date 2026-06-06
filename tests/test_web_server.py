from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from my_agent.web.server import make_handler
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
            )
            service.bootstrap()
            try:
                server = ThreadingHTTPServer(
                    ("127.0.0.1", 0),
                    make_handler(service=service, static_dir=root),
                )
            except PermissionError as exc:
                self.skipTest(f"socket binding is not allowed in this sandbox: {exc}")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}"
                topic = post_json(base + "/api/topic/refine", {"raw_input": "AI 产品怎么做"})
                self.assertIn("title", topic)
                clarified = post_json(
                    base + "/api/topic/refine",
                    {
                        "raw_input": "AI 产品怎么做",
                        "previous_topic": topic,
                        "clarification_answers": ["更关心 B 端付费验证"],
                    },
                )
                self.assertEqual(clarified["title"], "HTTP 精炼主题")
                self.assertEqual(clarified["clarification_round"], 1)
                self.assertEqual(clarified["refinement_source"], "llm")

                personas = get_json(base + "/api/personas")
                persona_id = personas[0]["id"]
                clone = post_json(
                    base + "/api/personas",
                    {"source_persona_id": persona_id, "display_name": "测试角色副本"},
                )
                self.assertNotEqual(clone["id"], persona_id)
                patched = request_json(
                    "PATCH",
                    base + f"/api/personas/{clone['id']}",
                    {
                        "display_name": "商业化测试角色",
                        "description": "专注商业化验证",
                        "categories": ["创业产品", "投资市场"],
                        "prompt": "只编辑 persona 副本，不修改原始 Skill。",
                    },
                )
                self.assertEqual(patched["display_name"], "商业化测试角色")
                self.assertIn("persona 副本", patched["prompt"])

                session = post_json(
                    base + "/api/sessions",
                    {
                        "raw_input": "AI 产品怎么做",
                        "topic": topic,
                        "persona_ids": [persona_id],
                    },
                )
                self.assertEqual(session["messages"][0]["role"], "user")

                updated = post_json(
                    base + f"/api/sessions/{session['id']}/messages",
                    {"content": "继续说商业化"},
                )
                self.assertGreaterEqual(len(updated["messages"]), 3)

                deleted = request_json("DELETE", base + f"/api/personas/{clone['id']}")
                self.assertTrue(deleted["archived"])
            finally:
                server.shutdown()
                thread.join(timeout=2)
                server.server_close()


def get_json(url: str):
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(url: str, payload: dict):
    return request_json("POST", url, payload)


def request_json(method: str, url: str, payload: dict | None = None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
