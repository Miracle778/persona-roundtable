from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from my_agent.core.models import PersonaSkill, now_iso
from my_agent.web.topic import TopicCard


DEFAULT_DB_PATH = Path.home() / ".local" / "share" / "my_agent" / "web.sqlite"


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    db_path = Path(path) if path is not None else default_db_path()
    if str(db_path) != ":memory:":
        db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys = on")
    return conn


def default_db_path() -> Path:
    override = os.environ.get("MY_AGENT_DB_PATH", "").strip()
    return Path(override).expanduser() if override else DEFAULT_DB_PATH


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        create table if not exists personas (
          id text primary key,
          source_skill_id text,
          source_skill_path text,
          name text not null,
          display_name text not null,
          description text not null default '',
          categories_json text not null default '[]',
          prompt text not null default '',
          role_rules text not null default '',
          provider_id text,
          model text,
          model_source text not null default 'inherit',
          enabled integer not null default 1,
          archived_at text,
          created_at text not null,
          updated_at text not null
        );

        create table if not exists sessions (
          id text primary key,
          title text not null,
          refined_topic text not null,
          topic_tags_json text not null default '[]',
          discussion_task text not null default '',
          raw_input text not null default '',
          source_summary text not null default '',
          style text not null default 'analysis',
          status text not null default 'draft',
          default_provider_id text,
          default_model text,
          created_at text not null,
          updated_at text not null
        );

        create table if not exists session_personas (
          session_id text not null references sessions(id) on delete cascade,
          persona_id text not null references personas(id),
          display_name_snapshot text not null,
          prompt_snapshot text not null default '',
          provider_id_snapshot text,
          model_snapshot text,
          position integer not null default 0,
          primary key (session_id, persona_id)
        );

        create table if not exists messages (
          id text primary key,
          session_id text not null references sessions(id) on delete cascade,
          role text not null,
          persona_id text,
          speaker text not null,
          content text not null,
          round_index integer not null default 0,
          provider_id text,
          model text,
          prompt_tokens integer,
          completion_tokens integer,
          total_tokens integer,
          latency_ms integer,
          error text,
          created_at text not null
        );

        create virtual table if not exists session_fts using fts5(
          session_id unindexed,
          title,
          refined_topic,
          tags,
          content
        );
        """
    )
    conn.commit()


def import_skills_as_personas(conn: sqlite3.Connection, skills: Iterable[PersonaSkill]) -> int:
    ensure_schema(conn)
    count = 0
    for skill in skills:
        persona_id = skill.id
        existing = conn.execute("select id from personas where id = ?", (persona_id,)).fetchone()
        if existing:
            continue
        now = now_iso()
        conn.execute(
            """
            insert into personas (
              id, source_skill_id, source_skill_path, name, display_name, description,
              categories_json, prompt, role_rules, created_at, updated_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                persona_id,
                skill.id,
                str(skill.source_path),
                skill.name,
                skill.display_name,
                skill.description,
                json.dumps(skill.categories, ensure_ascii=False),
                skill.raw_content,
                skill.role_rules,
                now,
                now,
            ),
        )
        count += 1
    conn.commit()
    return count


def list_personas(conn: sqlite3.Connection, include_archived: bool = False) -> list[dict[str, Any]]:
    ensure_schema(conn)
    where = "" if include_archived else "where archived_at is null"
    rows = conn.execute(
        f"select * from personas {where} order by display_name collate nocase"
    ).fetchall()
    return [persona_from_row(row) for row in rows]


def get_persona(
    conn: sqlite3.Connection,
    persona_id: str,
    include_archived: bool = False,
) -> dict[str, Any] | None:
    ensure_schema(conn)
    archived_clause = "" if include_archived else "and archived_at is null"
    row = conn.execute(
        f"select * from personas where id = ? {archived_clause}",
        (persona_id,),
    ).fetchone()
    return persona_from_row(row) if row else None


def clone_persona(
    conn: sqlite3.Connection,
    source_persona_id: str,
    display_name: str | None = None,
) -> str:
    ensure_schema(conn)
    source = conn.execute(
        "select * from personas where id = ? and archived_at is null",
        (source_persona_id,),
    ).fetchone()
    if not source:
        raise ValueError(f"找不到可复制的角色：{source_persona_id}")
    now = now_iso()
    clone_id = f"persona-{uuid4().hex[:10]}"
    clone_name = f"{source['name']}-copy"
    conn.execute(
        """
        insert into personas (
          id, source_skill_id, source_skill_path, name, display_name, description,
          categories_json, prompt, role_rules, provider_id, model, model_source,
          enabled, created_at, updated_at
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            clone_id,
            source["source_skill_id"],
            source["source_skill_path"],
            clone_name,
            display_name or f"{source['display_name']} 副本",
            source["description"],
            source["categories_json"],
            source["prompt"],
            source["role_rules"],
            source["provider_id"],
            source["model"],
            source["model_source"],
            1,
            now,
            now,
        ),
    )
    conn.commit()
    return clone_id


def update_persona(
    conn: sqlite3.Connection,
    persona_id: str,
    *,
    display_name: str | None = None,
    description: str | None = None,
    categories: list[str] | None = None,
    prompt: str | None = None,
) -> int:
    ensure_schema(conn)
    fields: list[str] = []
    values: list[Any] = []
    if display_name is not None:
        fields.append("display_name = ?")
        values.append(display_name)
    if description is not None:
        fields.append("description = ?")
        values.append(description)
    if categories is not None:
        fields.append("categories_json = ?")
        values.append(json.dumps(categories, ensure_ascii=False))
    if prompt is not None:
        fields.append("prompt = ?")
        values.append(prompt)
    if not fields:
        return 0
    fields.append("updated_at = ?")
    values.append(now_iso())
    values.append(persona_id)
    cursor = conn.execute(
        f"update personas set {', '.join(fields)} where id = ? and archived_at is null",
        values,
    )
    conn.commit()
    return cursor.rowcount


def archive_persona(conn: sqlite3.Connection, persona_id: str) -> int:
    ensure_schema(conn)
    now = now_iso()
    cursor = conn.execute(
        "update personas set archived_at = ?, updated_at = ? where id = ? and archived_at is null",
        (now, now, persona_id),
    )
    conn.commit()
    return cursor.rowcount


def assign_persona_model(
    conn: sqlite3.Connection,
    persona_ids: list[str],
    provider_id: str | None,
    model: str | None,
    model_source: str = "explicit",
) -> int:
    ensure_schema(conn)
    if not persona_ids:
        return 0
    now = now_iso()
    changed = 0
    for persona_id in persona_ids:
        cursor = conn.execute(
            """
            update personas
            set provider_id = ?, model = ?, model_source = ?, updated_at = ?
            where id = ? and archived_at is null
            """,
            (provider_id, model, model_source, now, persona_id),
        )
        changed += cursor.rowcount
    conn.commit()
    return changed


def create_session(
    conn: sqlite3.Connection,
    raw_input: str,
    topic: TopicCard,
    persona_ids: list[str],
    style: str = "analysis",
    default_provider_id: str | None = None,
    default_model: str | None = None,
) -> str:
    ensure_schema(conn)
    now = now_iso()
    session_id = uuid4().hex
    conn.execute(
        """
        insert into sessions (
          id, title, refined_topic, topic_tags_json, discussion_task, raw_input,
          source_summary, style, status, default_provider_id, default_model,
          created_at, updated_at
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            topic.title,
            topic.title,
            json.dumps(topic.tags, ensure_ascii=False),
            topic.discussion_task,
            raw_input,
            topic.source_summary,
            style,
            "draft",
            default_provider_id,
            default_model,
            now,
            now,
        ),
    )
    for index, persona_id in enumerate(persona_ids):
        persona = conn.execute("select * from personas where id = ?", (persona_id,)).fetchone()
        if not persona:
            continue
        conn.execute(
            """
            insert into session_personas (
              session_id, persona_id, display_name_snapshot, prompt_snapshot,
              provider_id_snapshot, model_snapshot, position
            ) values (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                persona_id,
                persona["display_name"],
                persona["prompt"],
                persona["provider_id"],
                persona["model"],
                index,
            ),
        )
    refresh_session_fts(conn, session_id)
    conn.commit()
    return session_id


def record_message(
    conn: sqlite3.Connection,
    session_id: str,
    role: str,
    speaker: str,
    content: str,
    persona_id: str | None = None,
    round_index: int = 0,
    provider_id: str | None = None,
    model: str | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    latency_ms: int | None = None,
    error: str | None = None,
) -> str:
    ensure_schema(conn)
    message_id = uuid4().hex
    conn.execute(
        """
        insert into messages (
          id, session_id, role, persona_id, speaker, content, round_index,
          provider_id, model, prompt_tokens, completion_tokens, total_tokens,
          latency_ms, error, created_at
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            message_id,
            session_id,
            role,
            persona_id,
            speaker,
            content,
            round_index,
            provider_id,
            model,
            prompt_tokens,
            completion_tokens,
            total_tokens,
            latency_ms,
            error,
            now_iso(),
        ),
    )
    conn.execute(
        "update sessions set updated_at = ?, status = ? where id = ?",
        (now_iso(), "active", session_id),
    )
    refresh_session_fts(conn, session_id)
    conn.commit()
    return message_id


def list_sessions(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    ensure_schema(conn)
    rows = conn.execute(
        """
        select s.*,
               count(m.id) as message_count
        from sessions s
        left join messages m on m.session_id = s.id
        group by s.id
        order by s.updated_at desc
        limit ?
        """,
        (limit,),
    ).fetchall()
    return [session_from_row(row) for row in rows]


def get_session(conn: sqlite3.Connection, session_id: str) -> dict[str, Any] | None:
    ensure_schema(conn)
    row = conn.execute("select * from sessions where id = ?", (session_id,)).fetchone()
    if not row:
        return None
    session = session_from_row(row)
    session["personas"] = [
        dict(item)
        for item in conn.execute(
            "select * from session_personas where session_id = ? order by position",
            (session_id,),
        ).fetchall()
    ]
    session["messages"] = [
        dict(item)
        for item in conn.execute(
            "select * from messages where session_id = ? order by created_at, rowid",
            (session_id,),
        ).fetchall()
    ]
    return session


def search_sessions(conn: sqlite3.Connection, query: str, limit: int = 50) -> list[dict[str, Any]]:
    ensure_schema(conn)
    cleaned = " ".join(query.split())
    if not cleaned:
        return list_sessions(conn, limit=limit)
    rows = []
    try:
        rows = conn.execute(
            """
            select s.*, count(m.id) as message_count
            from session_fts f
            join sessions s on s.id = f.session_id
            left join messages m on m.session_id = s.id
            where session_fts match ?
            group by s.id
            order by bm25(session_fts), s.updated_at desc
            limit ?
            """,
            (cleaned, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    if not rows:
        rows = search_sessions_like(conn, cleaned, limit)
    return [session_from_row(row) for row in rows]


def search_sessions_like(conn: sqlite3.Connection, query: str, limit: int) -> list[sqlite3.Row]:
    like = f"%{query}%"
    return conn.execute(
        """
        select s.*, count(m.id) as message_count
        from sessions s
        left join messages m on m.session_id = s.id
        where s.title like ? or s.refined_topic like ? or m.content like ?
        group by s.id
        order by s.updated_at desc
        limit ?
        """,
        (like, like, like, limit),
    ).fetchall()


def refresh_session_fts(conn: sqlite3.Connection, session_id: str) -> None:
    session = conn.execute("select * from sessions where id = ?", (session_id,)).fetchone()
    if not session:
        return
    message_text = "\n".join(
        row["content"]
        for row in conn.execute(
            "select content from messages where session_id = ? order by created_at, rowid",
            (session_id,),
        ).fetchall()
    )
    tags = " ".join(json.loads(session["topic_tags_json"] or "[]"))
    conn.execute("delete from session_fts where session_id = ?", (session_id,))
    conn.execute(
        "insert into session_fts(session_id, title, refined_topic, tags, content) values (?, ?, ?, ?, ?)",
        (session_id, session["title"], session["refined_topic"], tags, message_text),
    )


def persona_from_row(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["categories"] = json.loads(data.pop("categories_json") or "[]")
    data["enabled"] = bool(data["enabled"])
    return data


def session_from_row(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["topic_tags"] = json.loads(data.pop("topic_tags_json") or "[]")
    data["message_count"] = int(data.get("message_count") or 0)
    return data
