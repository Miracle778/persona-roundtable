from __future__ import annotations

import json
import unittest

from my_agent.web.topic import refine_topic


class FakeLLM:
    def __init__(self, payload: dict):
        self.payload = payload
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return json.dumps(self.payload, ensure_ascii=False)


class TopicRefinementTests(unittest.TestCase):
    def test_refine_topic_builds_confirmable_topic_card(self) -> None:
        card = refine_topic("我想聊聊 AI 最新模型发布后，程序员就业会不会被冲击")

        self.assertIn("AI", card.title)
        self.assertIn("创业产品", card.tags)
        self.assertIn("社会观察", card.tags)
        self.assertIn("请围绕", card.discussion_task)
        self.assertLessEqual(card.clarification_round_limit, 3)

    def test_refine_topic_uses_title_when_available(self) -> None:
        card = refine_topic(
            "原始正文很长",
            title="知乎热帖：小红书内容分析产品有没有机会",
        )

        self.assertEqual(card.title, "知乎热帖：小红书内容分析产品有没有机会")
        self.assertIn("创业产品", card.tags)

    def test_refine_topic_uses_llm_structured_card_and_clarification_questions(self) -> None:
        llm = FakeLLM(
            {
                "title": "AI 工程化岗位转型判断",
                "tags": ["创业产品", "社会观察"],
                "discussion_task": "判断 AI 工程化变化对程序员岗位和产品机会的影响。",
                "source_summary": "用户想讨论 AI 工程化对就业的影响。",
                "suggested_agent_ids": ["weirdo-tv-musk"],
                "clarification_questions": ["你更关心个人转型，还是产品机会？"],
            }
        )

        card = refine_topic("AI 工程化", llm_client=llm)

        self.assertEqual(card.title, "AI 工程化岗位转型判断")
        self.assertEqual(card.tags, ["创业产品", "社会观察"])
        self.assertEqual(card.suggested_agent_ids, ["weirdo-tv-musk"])
        self.assertEqual(card.clarification_questions, ["你更关心个人转型，还是产品机会？"])
        self.assertEqual(card.clarification_round, 0)
        self.assertEqual(card.refinement_source, "llm")
        self.assertIn("JSON", llm.prompts[0])

    def test_refine_topic_tracks_answers_and_caps_clarification_rounds(self) -> None:
        llm = FakeLLM(
            {
                "title": "AI 产品商业化路径",
                "tags": ["创业产品"],
                "discussion_task": "收束 AI 产品的付费验证路径。",
                "source_summary": "用户已经补充更关心商业化。",
                "clarification_questions": ["模型仍想继续追问，但应该被截断。"],
            }
        )

        card = refine_topic(
            "AI 产品怎么做",
            clarification_answers=["更关心 B 端付费验证"],
            previous_topic={"title": "AI 产品机会", "clarification_round": 2},
            llm_client=llm,
        )

        self.assertEqual(card.clarification_round, 3)
        self.assertEqual(card.clarification_questions, [])
        self.assertIn("更关心 B 端付费验证", llm.prompts[0])


if __name__ == "__main__":
    unittest.main()
