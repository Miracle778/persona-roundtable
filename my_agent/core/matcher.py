from __future__ import annotations

from collections import Counter

from my_agent.core.models import AgentSelection, PersonaSkill
from my_agent.core.skill_loader import CATEGORY_KEYWORDS


def detect_categories(question: str) -> list[str]:
    scores: Counter[str] = Counter()
    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in question.lower():
                scores[category] += max(1, len(keyword) // 2)
    return [category for category, _ in scores.most_common()] or ["通用讨论"]


def select_agents(
    question: str,
    skills: list[PersonaSkill],
    agent_ids: list[str] | None = None,
    max_agents: int = 4,
) -> tuple[list[str], list[AgentSelection]]:
    if agent_ids:
        wanted = {item.strip() for item in agent_ids}
        selections = [
            AgentSelection(skill=skill, score=999, matched_terms=["manual"])
            for skill in skills
            if skill.id in wanted or skill.name in wanted or skill.display_name in wanted
        ]
        return detect_categories(question), selections

    detected = detect_categories(question)
    selections: list[AgentSelection] = []
    for skill in skills:
        score = 0
        matched_terms: list[str] = []

        for category in detected:
            if category in skill.categories:
                score += 10
                matched_terms.append(category)

        for term in skill.triggers + skill.suitable_for + skill.categories:
            if term and term.lower() in question.lower():
                score += 8
                matched_terms.append(term)

        for category in skill.categories:
            if category in {"人际关系", "社会观察", "战略决策"}:
                score += 1

        if score > 0:
            selections.append(AgentSelection(skill=skill, score=score, matched_terms=unique(matched_terms)))

    selections.sort(key=lambda item: item.score, reverse=True)
    if not selections:
        selections = [AgentSelection(skill=skill, score=1, matched_terms=["fallback"]) for skill in skills[:max_agents]]
    return detected, selections[:max_agents]


def unique(items: list[str]) -> list[str]:
    result = []
    seen = set()
    for item in items:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result
