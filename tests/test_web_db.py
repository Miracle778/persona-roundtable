from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from my_agent.core.models import PersonaSkill
from my_agent.web.db import (
    assign_persona_model,
    archive_persona,
    clone_persona,
    connect,
    create_session,
    ensure_schema,
    import_skills_as_personas,
    list_personas,
    list_sessions,
    record_message,
    search_sessions,
    update_persona,
)
from my_agent.web.topic import TopicCard


class WebDatabaseTests(unittest.TestCase):
    def test_persona_import_session_message_and_search(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            conn = connect(Path(tmp) / "app.sqlite")
            try:
                ensure_schema(conn)
                skill = PersonaSkill(
                    id="test-skill",
                    name="test-skill",
                    display_name="测试角色",
                    description="用于测试的角色",
                    source_path=Path("skills/test/SKILL.md"),
                    raw_content="# 测试角色\n\n## 角色扮演规则\n保持清晰。",
                    categories=["创业产品"],
                    role_rules="保持清晰。",
                )

                import_skills_as_personas(conn, [skill])
                personas = list_personas(conn)
                self.assertEqual(len(personas), 1)
                self.assertEqual(personas[0]["source_skill_id"], "test-skill")
                assign_persona_model(
                    conn,
                    persona_ids=[personas[0]["id"]],
                    provider_id="openai",
                    model="gpt-4o-mini",
                )
                personas = list_personas(conn)
                self.assertEqual(personas[0]["provider_id"], "openai")
                self.assertEqual(personas[0]["model"], "gpt-4o-mini")
                self.assertEqual(personas[0]["model_source"], "explicit")

                session_id = create_session(
                    conn,
                    raw_input="讨论一个 AI 产品",
                    topic=TopicCard(
                        title="AI 产品机会判断",
                        tags=["创业产品"],
                        discussion_task="请围绕 AI 产品机会判断展开讨论。",
                        source_summary="讨论一个 AI 产品",
                        suggested_agent_ids=["test-skill"],
                        clarification_round_limit=3,
                    ),
                    persona_ids=[personas[0]["id"]],
                )
                record_message(
                    conn,
                    session_id=session_id,
                    role="persona",
                    speaker="测试角色",
                    content="这个 AI 产品要先验证用户是否付费。",
                    persona_id=personas[0]["id"],
                    provider_id="openai",
                    model="gpt-4o-mini",
                    total_tokens=42,
                    latency_ms=120,
                )

                sessions = list_sessions(conn)
                self.assertEqual(sessions[0]["title"], "AI 产品机会判断")
                self.assertEqual(sessions[0]["message_count"], 1)
                matches = search_sessions(conn, "付费")
                self.assertEqual([item["id"] for item in matches], [session_id])
            finally:
                conn.close()

    def test_schema_is_idempotent(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            ensure_schema(conn)
            ensure_schema(conn)
            tables = {
                row[0]
                for row in conn.execute(
                    "select name from sqlite_master where type in ('table', 'view')"
                )
            }
            self.assertIn("sessions", tables)
            self.assertIn("messages", tables)
            self.assertIn("personas", tables)
        finally:
            conn.close()

    def test_clone_update_and_archive_persona_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            conn = connect(Path(tmp) / "app.sqlite")
            try:
                skill = PersonaSkill(
                    id="test-skill",
                    name="test-skill",
                    display_name="测试角色",
                    description="用于测试的角色",
                    source_path=Path("skills/test/SKILL.md"),
                    raw_content="# 测试角色\n\n## 角色扮演规则\n保持清晰。",
                    categories=["创业产品"],
                    role_rules="保持清晰。",
                )
                import_skills_as_personas(conn, [skill])
                source = list_personas(conn)[0]

                clone_id = clone_persona(conn, source["id"], display_name="测试角色副本")
                self.assertNotEqual(clone_id, source["id"])
                clone = [item for item in list_personas(conn) if item["id"] == clone_id][0]
                self.assertEqual(clone["source_skill_id"], source["source_skill_id"])
                self.assertEqual(clone["display_name"], "测试角色副本")

                changed = update_persona(
                    conn,
                    clone_id,
                    display_name="商业化测试角色",
                    description="专注商业化验证",
                    categories=["创业产品", "投资市场"],
                    prompt="只编辑 persona 副本，不修改原始 Skill。",
                )
                self.assertEqual(changed, 1)
                updated = [item for item in list_personas(conn) if item["id"] == clone_id][0]
                self.assertEqual(updated["display_name"], "商业化测试角色")
                self.assertEqual(updated["categories"], ["创业产品", "投资市场"])
                self.assertIn("persona 副本", updated["prompt"])

                archived = archive_persona(conn, clone_id)
                self.assertEqual(archived, 1)
                self.assertEqual([item["id"] for item in list_personas(conn)], [source["id"]])
                archived_items = list_personas(conn, include_archived=True)
                self.assertIn(clone_id, [item["id"] for item in archived_items])
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
