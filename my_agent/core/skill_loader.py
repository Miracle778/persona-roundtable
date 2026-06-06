from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from my_agent.core.models import PersonaSkill


CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "两性情感": ["两性", "恋爱", "爱情", "亲密", "伴侣", "对象", "男朋友", "女朋友", "婚姻", "彩礼", "分手", "暧昧", "情感", "吸引力", "性压抑", "连接"],
    "人际关系": ["人际", "关系", "沟通", "社交", "朋友", "台阶", "真诚", "冲突", "边界", "边界感", "吵架"],
    "社会观察": ["社会", "底层", "阶层", "纪实", "人性", "群体", "现实", "就业", "失业", "裁员", "产业", "技术变革"],
    "战略决策": ["战略", "主要矛盾", "组织", "竞争", "实践", "持久战", "统一战线", "破局", "制裁", "自主可控"],
    "创业产品": ["创业", "产品", "MVP", "用户", "市场", "商业", "增长", "AI", "人工智能", "模型", "程序员", "技术"],
    "投资市场": ["A股", "投资", "股票", "市场", "蓝筹", "散户", "政策市", "估值", "股息"],
    "自我成长": ["成长", "自律", "读书", "健身", "低谷", "选择", "职业", "人生", "转型", "技能"],
}


def load_skills(skill_dirs: Iterable[Path]) -> list[PersonaSkill]:
    skills: list[PersonaSkill] = []
    for skill_dir in skill_dirs:
        if not skill_dir.exists():
            continue
        for path in sorted(skill_dir.rglob("SKILL.md")):
            if ".git" in path.parts:
                continue
            skills.append(load_markdown_skill(path))
    return skills


def load_markdown_skill(path: Path) -> PersonaSkill:
    raw = path.read_text(encoding="utf-8")
    frontmatter, body = split_frontmatter(raw)
    name = frontmatter.get("name") or path.parent.name
    description = frontmatter.get("description") or first_paragraph(body)
    display_name = infer_display_name(body, name)
    triggers = frontmatter_list(frontmatter, "triggers") or extract_list_after_labels(raw, ["触发词", "核心触发词"])
    suitable_for = frontmatter_list(frontmatter, "suitable_for") or extract_list_after_labels(raw, ["适合场景", "适合"])
    not_suitable_for = frontmatter_list(frontmatter, "not_suitable_for") or extract_list_after_labels(raw, ["不适合场景", "明确不激活", "局限"])
    categories = frontmatter_list(frontmatter, "categories") or infer_categories(raw, suitable_for)
    role_rules = extract_section(body, "角色扮演规则") or extract_section(body, "回答规矩") or ""
    voice_style = frontmatter_map(frontmatter, "voice_style")
    visual_style = frontmatter_map(frontmatter, "visual_style")

    return PersonaSkill(
        id=slugify(name or path.parent.name),
        name=name,
        display_name=display_name,
        description=description.strip(),
        source_path=path,
        raw_content=raw,
        categories=categories,
        suitable_for=suitable_for,
        not_suitable_for=not_suitable_for,
        triggers=triggers,
        role_rules=role_rules.strip(),
        voice_style=voice_style,
        visual_style=visual_style,
        metadata={key: value for key, value in frontmatter.items() if key not in {"name", "description"}},
    )


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, flags=re.S)
    if not match:
        return {}, text
    block, body = match.groups()
    result: dict[str, str] = {}
    current_key: str | None = None
    current_lines: list[str] = []
    for line in block.splitlines():
        key_match = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if key_match and not line.startswith(" "):
            if current_key:
                result[current_key] = "\n".join(current_lines).strip()
            current_key = key_match.group(1)
            value = key_match.group(2)
            current_lines = [] if value == "|" else [value]
        elif current_key:
            current_lines.append(line.strip())
    if current_key:
        result[current_key] = "\n".join(current_lines).strip()
    return result, body


def frontmatter_list(frontmatter: dict[str, str], key: str) -> list[str]:
    value = frontmatter.get(key, "")
    if not value:
        return []
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    if any(line.startswith("- ") for line in lines):
        return unique_keep_order(line[2:].strip() for line in lines if line.startswith("- "))
    return split_terms(value)


def frontmatter_map(frontmatter: dict[str, str], key: str) -> dict[str, str]:
    value = frontmatter.get(key, "")
    if not value:
        return {}
    result: dict[str, str] = {}
    for line in value.splitlines():
        if ":" not in line:
            continue
        item_key, item_value = line.split(":", 1)
        result[item_key.strip()] = item_value.strip().strip('"')
    return result


def first_paragraph(body: str) -> str:
    for chunk in re.split(r"\n\s*\n", body):
        clean = re.sub(r"^[#>\s]+", "", chunk.strip())
        if clean:
            return clean
    return ""


def infer_display_name(body: str, fallback: str) -> str:
    h1 = re.search(r"^#\s+(.+)$", body, flags=re.M)
    if h1:
        return h1.group(1).strip()
    return fallback.replace("-skill", "").replace("-perspective", "").replace("-", " ")


def extract_list_after_labels(text: str, labels: list[str]) -> list[str]:
    found: list[str] = []
    for label in labels:
        match = re.search(rf"{re.escape(label)}(?:（[^）]*）)?[：:]\s*([^\n]*)", text)
        if match:
            captured = match.group(1).strip()
            if not captured:
                next_line = text[match.end():].splitlines()
                captured = next_line[0].strip() if next_line else ""
            found.extend(split_terms(captured))
    return unique_keep_order(found)


def split_terms(text: str) -> list[str]:
    text = re.sub(r"[「」『』【】\[\]（）()]", " ", text)
    terms = re.split(r"[、,，/；;。\n\s]+", text)
    return [term.strip(" -\t") for term in terms if 1 < len(term.strip(" -\t")) <= 30]


def infer_categories(text: str, suitable_for: list[str]) -> list[str]:
    haystack = text + "\n" + "\n".join(suitable_for)
    scored: list[tuple[str, int]] = []
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = sum(haystack.count(keyword) for keyword in keywords)
        if score:
            scored.append((category, score))
    scored.sort(key=lambda item: item[1], reverse=True)
    return [category for category, _ in scored[:4]]


def extract_section(body: str, heading: str) -> str:
    pattern = rf"^##\s+{re.escape(heading)}\s*$([\s\S]*?)(?=^##\s+|\Z)"
    match = re.search(pattern, body, flags=re.M)
    return match.group(1).strip() if match else ""


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", value)
    return value.strip("-") or "skill"


def unique_keep_order(items: Iterable[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item and item not in seen:
            result.append(item)
            seen.add(item)
    return result
