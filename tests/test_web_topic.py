from __future__ import annotations

import unittest

from my_agent.web.topic import refine_topic


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


if __name__ == "__main__":
    unittest.main()
