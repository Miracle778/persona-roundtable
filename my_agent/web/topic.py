from __future__ import annotations

import json
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
    clarification_questions: list[str] = field(default_factory=list)
    clarification_round: int = 0
    refinement_source: str = "local"
    fallback_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def refine_topic(
    raw_input: str,
    title: str | None = None,
    clarification_answers: list[str] | None = None,
    previous_topic: dict[str, Any] | TopicCard | None = None,
    llm_client: Any | None = None,
) -> TopicCard:
    round_index = next_clarification_round(previous_topic, clarification_answers or [])
    if llm_client is not None:
        try:
            prompt = build_topic_refinement_prompt(
                raw_input=raw_input,
                title=title,
                clarification_answers=clarification_answers or [],
                previous_topic=previous_topic,
                clarification_round=round_index,
            )
            return parse_llm_topic_card(
                llm_client.complete(prompt),
                raw_input=raw_input,
                title=title,
                clarification_round=round_index,
            )
        except Exception as exc:
            return build_local_topic_card(
                raw_input=raw_input,
                title=title,
                clarification_round=round_index,
                refinement_source="fallback",
                fallback_reason=str(exc),
            )
    return build_local_topic_card(
        raw_input=raw_input,
        title=title,
        clarification_round=round_index,
    )


def build_local_topic_card(
    raw_input: str,
    title: str | None = None,
    clarification_round: int = 0,
    refinement_source: str = "local",
    fallback_reason: str | None = None,
) -> TopicCard:
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
        clarification_questions=[],
        clarification_round=min(max(clarification_round, 0), 3),
        refinement_source=refinement_source,
        fallback_reason=fallback_reason,
    )


def build_topic_refinement_prompt(
    raw_input: str,
    title: str | None,
    clarification_answers: list[str],
    previous_topic: dict[str, Any] | TopicCard | None,
    clarification_round: int,
) -> str:
    previous = previous_topic.to_dict() if isinstance(previous_topic, TopicCard) else previous_topic
    return f"""
你是多角色讨论工作台的议题编辑。请把用户的原始输入精炼成正式讨论话题卡。

要求：
- 只输出一个 JSON 对象，不要 Markdown。
- title 不能只是截取原文，必须概括清楚讨论对象和判断角度。
- tags 从业务/社会/技术/关系等角度给 1-4 个中文标签。
- discussion_task 要说明讨论要解决什么问题。
- clarification_questions 最多 2 个；只有信息不足以开聊时才问。
- 当前澄清轮次是 {clarification_round}/3；到第 3 轮必须停止追问，clarification_questions 返回 []。

JSON 字段：
title: string
tags: string[]
discussion_task: string
source_summary: string
suggested_agent_ids: string[]
clarification_questions: string[]

原始输入：
{raw_input}

用户提供的标题：
{title or ""}

上一轮信息：
{json.dumps(previous or {}, ensure_ascii=False)}

用户澄清回答：
{json.dumps(clarification_answers, ensure_ascii=False)}
""".strip()


def parse_llm_topic_card(
    text: str,
    raw_input: str,
    title: str | None,
    clarification_round: int,
) -> TopicCard:
    data = parse_json_object(text)
    topic_title = str(data.get("title") or "").strip() or compact_title(title or raw_input)
    tags = list_of_strings(data.get("tags")) or infer_tags(f"{title or ''}\n{raw_input}")
    questions = list_of_strings(data.get("clarification_questions"))[:2]
    capped_round = min(max(clarification_round, 0), 3)
    if capped_round >= 3:
        questions = []
    return TopicCard(
        title=topic_title,
        tags=tags[:4],
        discussion_task=str(data.get("discussion_task") or "").strip()
        or f"请围绕「{topic_title}」展开多角色讨论。",
        source_summary=str(data.get("source_summary") or "").strip() or compact_summary(raw_input),
        suggested_agent_ids=list_of_strings(data.get("suggested_agent_ids")),
        clarification_round_limit=3,
        clarification_questions=questions,
        clarification_round=capped_round,
        refinement_source="llm",
    )


def parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped, flags=re.IGNORECASE).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("LLM topic refinement did not return a JSON object")
    data = json.loads(stripped[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("LLM topic refinement JSON root must be an object")
    return data


def list_of_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def next_clarification_round(
    previous_topic: dict[str, Any] | TopicCard | None,
    clarification_answers: list[str],
) -> int:
    if isinstance(previous_topic, TopicCard):
        previous_round = previous_topic.clarification_round
    elif isinstance(previous_topic, dict):
        try:
            previous_round = int(previous_topic.get("clarification_round") or 0)
        except (TypeError, ValueError):
            previous_round = 0
    else:
        previous_round = 0
    if clarification_answers:
        previous_round += 1
    return min(max(previous_round, 0), 3)


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
