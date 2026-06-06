from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from my_agent.core.skill_loader import CATEGORY_KEYWORDS


@dataclass(frozen=True)
class TopicCard:
    title: str
    tags: list[str]
    discussion_task: str
    source_summary: str
    suggested_agent_ids: list[str] = field(default_factory=list)
    clarification_round_limit: int = 3

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def refine_topic(raw_input: str, title: str | None = None) -> TopicCard:
    normalized = normalize_text(title or raw_input)
    topic_title = compact_title(normalized)
    tags = infer_tags(f"{title or ''}\n{raw_input}")
    source_summary = compact_summary(raw_input)
    discussion_task = (
        f"请围绕「{topic_title}」展开多角色讨论：先明确事实和关键分歧，"
        "再给出不同角色的判断依据，最后收束为可执行建议。"
    )
    return TopicCard(
        title=topic_title,
        tags=tags,
        discussion_task=discussion_task,
        source_summary=source_summary,
        suggested_agent_ids=[],
        clarification_round_limit=3,
    )


def normalize_text(value: str) -> str:
    text = re.sub(r"\s+", " ", value).strip()
    return text or "未命名讨论"


def compact_title(value: str, limit: int = 42) -> str:
    text = normalize_text(value)
    text = re.sub(r"^(我想聊聊|我想讨论|聊聊|讨论一下|关于)", "", text).strip(" ：:，,。")
    if len(text) <= limit:
        return text
    cut = text[:limit]
    punctuation = max(cut.rfind(mark) for mark in ["。", "，", "；", "？", "！", ",", ";", "?", "!"])
    if punctuation >= 12:
        return cut[:punctuation].strip()
    return cut.rstrip("，,；;：:、 ") + "..."


def compact_summary(value: str, limit: int = 180) -> str:
    text = normalize_text(value)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip("，,；;：:、 ") + "…"


def infer_tags(text: str) -> list[str]:
    haystack = text.lower()
    scored: list[tuple[str, int]] = []
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = 0
        for keyword in keywords:
            key = keyword.lower()
            score += haystack.count(key)
        if score:
            scored.append((category, score))
    scored.sort(key=lambda item: item[1], reverse=True)
    return [category for category, _ in scored[:4]] or ["通用讨论"]

