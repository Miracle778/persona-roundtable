from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from my_agent.web.service import WebAppService


class FakeTopicLLM:
    def __init__(self):
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return json.dumps(
            {
                "title": "AI 商业化验证主题",
                "tags": ["创业产品"],
                "discussion_task": "围绕 AI 产品商业化验证展开讨论。",
                "source_summary": "用户补充了付费验证方向。",
                "clarification_questions": [],
            },
            ensure_ascii=False,
        )


class WebAppServiceTests(unittest.TestCase):
    def test_bootstrap_imports_skills_and_creates_discussion_session(self) -> None:
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

保持清晰，先判断用户是否付费。
""",
                encoding="utf-8",
            )
            service = WebAppService(
                db_path=root / "web.sqlite",
                config_path=root / "config.json",
                skill_dirs=[root / "skills"],
            )

            service.bootstrap()
            personas = service.list_personas()
            self.assertEqual(len(personas), 1)
            service.assign_persona_model(
                persona_ids=[personas[0]["id"]],
                provider_id="openai",
                model="gpt-4o-mini",
            )
            personas = service.list_personas()
            self.assertEqual(personas[0]["model"], "gpt-4o-mini")

            topic = service.refine_topic("我想讨论 AI 产品机会")
            session = service.create_session(
                raw_input="我想讨论 AI 产品机会",
                topic=topic,
                persona_ids=[personas[0]["id"]],
            )

            self.assertEqual(session["title"], topic["title"])
            self.assertEqual(len(session["messages"]), 1)
            self.assertEqual(session["messages"][0]["role"], "user")

            updated = service.continue_session(session["id"], "请继续从商业化角度说")
            persona_messages = [
                item for item in updated["messages"] if item["role"] == "persona"
            ]
            self.assertEqual(len(persona_messages), 1)
            self.assertIn("商业化", persona_messages[0]["content"])
            self.assertEqual(persona_messages[0]["model"], "gpt-4o-mini")

    def test_clone_update_and_archive_persona_copy(self) -> None:
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
            )
            service.bootstrap()
            source = service.list_personas()[0]

            clone = service.clone_persona(source["id"], display_name="测试角色副本")
            self.assertNotEqual(clone["id"], source["id"])
            self.assertEqual(clone["source_skill_id"], source["source_skill_id"])

            updated = service.update_persona(
                clone["id"],
                {
                    "display_name": "商业化测试角色",
                    "description": "专注商业化验证",
                    "categories": ["创业产品", "投资市场"],
                    "prompt": "只编辑 persona 副本，不修改原始 Skill。",
                },
            )
            self.assertEqual(updated["display_name"], "商业化测试角色")
            self.assertEqual(updated["categories"], ["创业产品", "投资市场"])
            self.assertIn("persona 副本", updated["prompt"])

            archived = service.archive_persona(clone["id"])
            self.assertEqual(archived["archived"], True)
            self.assertEqual([item["id"] for item in service.list_personas()], [source["id"]])

    def test_refine_topic_uses_injected_llm_and_clarification_answers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            topic_llm = FakeTopicLLM()
            service = WebAppService(
                db_path=root / "web.sqlite",
                config_path=root / "config.json",
                skill_dirs=[root / "skills"],
                topic_llm_client=topic_llm,
            )

            card = service.refine_topic(
                "AI 产品怎么做",
                clarification_answers=["更关心 B 端付费验证"],
                previous_topic={"title": "AI 产品机会", "clarification_round": 1},
            )

            self.assertEqual(card["title"], "AI 商业化验证主题")
            self.assertEqual(card["clarification_round"], 2)
            self.assertEqual(card["refinement_source"], "llm")
            self.assertIn("更关心 B 端付费验证", topic_llm.prompts[0])


if __name__ == "__main__":
    unittest.main()
