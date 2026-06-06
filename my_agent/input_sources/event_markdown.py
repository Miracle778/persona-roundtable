from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from my_agent.core.models import NormalizedInput
from my_agent.core.progress import ProgressCallback, noop_progress


EVENT_VERSION = "1"


def save_discussion_event_markdown(
    normalized: NormalizedInput,
    event_dir: Path,
    progress: ProgressCallback = noop_progress,
) -> Path:
    event_dir.mkdir(parents=True, exist_ok=True)
    platform = normalized.platform or str(normalized.metadata.get("platform") or "manual")
    slug = slugify(normalized.title or normalized.source_url or normalized.raw_input or "event")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = event_dir / f"{stamp}-{platform}-{slug}.md"
    path.write_text(render_discussion_event_markdown(normalized), encoding="utf-8")
    progress(f"[extract-url] 讨论事件已保存：{path}")
    return path


def render_discussion_event_markdown(normalized: NormalizedInput) -> str:
    extracted_at = normalized.metadata.get("extracted_at") or datetime.now().astimezone().isoformat(timespec="seconds")
    source_type = "social_post" if normalized.type == "url" else normalized.type
    comments = normalized.comments or []
    comment_threads = normalized.metadata.get("comment_threads") or []
    event_brief = build_event_brief(normalized)
    background = normalized.metadata.get("background_context") or {}
    frontmatter = {
        "my_agent_event_version": EVENT_VERSION,
        "event_type": source_type,
        "platform": normalized.platform or "",
        "source_url": normalized.source_url or "",
        "title": normalized.title or "",
        "author": normalized.author or "",
        "extracted_at": str(extracted_at),
        "topic_angle": event_brief["topic_angle"],
        "opening_hook": event_brief["opening_hook"],
    }
    body = clean_body_for_event(extract_section(normalized.content, "【正文】", "【可见评论】") or normalized.content)
    task = extract_section(normalized.content, "【讨论任务】", None) or default_discussion_task()
    return "\n".join(
        [
            "---",
            *[f"{key}: {quote_meta(value)}" for key, value in frontmatter.items()],
            "---",
            "",
            f"# 讨论事件：{normalized.title or default_title(normalized)}",
            "",
            "## 事件来源",
            "",
            f"- 平台：{normalized.platform or '未知'}",
            f"- 链接：{normalized.source_url or '无'}",
            f"- 标题：{normalized.title or '未提取到标题'}",
            f"- 作者：{normalized.author or '未提取到作者'}",
            f"- 提取时间：{extracted_at}",
            "",
            "## 选题判断",
            "",
            f"- 选题角度：{event_brief['topic_angle']}",
            f"- 开场钩子：{event_brief['opening_hook']}",
            "- 核心争议：",
            *[f"  - {item}" for item in event_brief["conflict_points"]],
            "- 评论区阵营：",
            *[f"  - {item}" for item in event_brief["comment_camps"]],
            "",
            "## 原帖正文",
            "",
            body.strip() or "未提取到正文。",
            "",
            "## 评论区摘录",
            "",
            render_comments(comments, comment_threads),
            "",
            "## 背景补全",
            "",
            render_background(background),
            "",
            "## 讨论任务",
            "",
            task.strip(),
            "",
        ]
    )


def load_discussion_event_markdown(
    path: Path,
    progress: ProgressCallback = noop_progress,
) -> NormalizedInput:
    progress("[3/8] 检测到 Markdown 讨论事件，正在加载...")
    text = path.expanduser().read_text(encoding="utf-8")
    metadata, content_text = parse_frontmatter(text)
    title = str(metadata.get("title") or parse_heading(content_text) or path.stem).strip()
    source_url = str(metadata.get("source_url") or "").strip() or None
    platform = str(metadata.get("platform") or "").strip() or None
    author = str(metadata.get("author") or "").strip() or None
    comments_section = parse_markdown_section(content_text, "评论区摘录")
    comments = parse_comment_lines(comments_section)
    topic_brief = parse_markdown_section(content_text, "选题判断")
    background_section = parse_markdown_section(content_text, "背景补全")
    discussion_content = build_content_from_event_markdown(content_text, metadata)
    return NormalizedInput(
        type="event_markdown",
        raw_input=str(path),
        content=discussion_content,
        title=title,
        source_url=source_url,
        platform=platform,
        author=author,
        comments=comments,
        metadata={
            **metadata,
            "source": "discussion_event_markdown",
            "event_markdown_path": str(path.expanduser()),
            "topic_brief": topic_brief,
            "background_markdown": background_section,
        },
    )


def with_event_markdown_path(normalized: NormalizedInput, path: Path) -> NormalizedInput:
    return replace(
        normalized,
        metadata={
            **normalized.metadata,
            "event_markdown_path": str(path),
        },
    )


def edit_discussion_event_markdown(
    path: Path,
    updates: dict[str, str],
    task: str | None = None,
) -> Path:
    text = path.expanduser().read_text(encoding="utf-8")
    metadata, body = parse_frontmatter(text)
    metadata.update(updates)
    if task is not None:
        body = replace_markdown_section(body, "讨论任务", task.strip())
    if updates:
        body = update_topic_section(body, updates)
    frontmatter = "\n".join(f"{key}: {quote_meta(value)}" for key, value in metadata.items())
    path.expanduser().write_text(f"---\n{frontmatter}\n---\n\n{body.lstrip()}", encoding="utf-8")
    return path


def build_content_from_event_markdown(content_text: str, metadata: dict[str, Any]) -> str:
    source = parse_markdown_section(content_text, "事件来源")
    topic_brief = parse_markdown_section(content_text, "选题判断")
    body = parse_markdown_section(content_text, "原帖正文")
    comments = parse_markdown_section(content_text, "评论区摘录")
    background = parse_markdown_section(content_text, "背景补全")
    task = parse_markdown_section(content_text, "讨论任务") or default_discussion_task()
    return "\n".join(
        [
            "【内容来源】",
            source.strip() or render_source_from_metadata(metadata),
            "",
            "【选题判断】",
            topic_brief.strip() or render_topic_brief_from_metadata(metadata),
            "",
            "【正文】",
            body.strip() or "未提取到正文。",
            "",
            "【可见评论】",
            comments.strip() or "未提取到可见评论。",
            "",
            "【背景补全】",
            background.strip() or "无背景补全。",
            "",
            "【讨论任务】",
            task.strip(),
        ]
    )


def render_comments(comments: list[str], comment_threads: Any) -> str:
    if comment_threads:
        lines: list[str] = []
        for index, thread in enumerate(comment_threads, start=1):
            if not isinstance(thread, dict):
                continue
            author = thread.get("author") or "匿名用户"
            content = thread.get("content") or ""
            lines.append(f"{index}. {author}：{content}")
            replies = thread.get("replies") or []
            if replies:
                lines.append("   回复：")
            for reply in replies:
                if isinstance(reply, dict):
                    reply_author = reply.get("author") or "匿名用户"
                    reply_content = reply.get("content") or ""
                    lines.append(f"   - {reply_author}：{reply_content}")
        if lines:
            return "\n".join(lines)
    if comments:
        return "\n".join(f"{index}. {comment}" for index, comment in enumerate(comments, start=1))
    return "未提取到可见评论。"


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text
    raw_meta = text[4:end].strip()
    body = text[end + len("\n---"):].lstrip("\n")
    metadata: dict[str, str] = {}
    for line in raw_meta.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = unquote_meta(value.strip())
    return metadata, body


def parse_heading(text: str) -> str | None:
    match = re.search(r"^#\s+讨论事件[:：]\s*(.+)$", text, flags=re.MULTILINE)
    if match:
        return match.group(1).strip()
    match = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
    return match.group(1).strip() if match else None


def parse_markdown_section(text: str, heading: str) -> str:
    pattern = rf"^##\s+{re.escape(heading)}\s*$"
    match = re.search(pattern, text, flags=re.MULTILINE)
    if not match:
        return ""
    start = match.end()
    next_match = re.search(r"^##\s+", text[start:], flags=re.MULTILINE)
    end = start + next_match.start() if next_match else len(text)
    return text[start:end].strip()


def replace_markdown_section(text: str, heading: str, replacement: str) -> str:
    pattern = rf"^##\s+{re.escape(heading)}\s*$"
    match = re.search(pattern, text, flags=re.MULTILINE)
    if not match:
        suffix = "\n" if text.endswith("\n") else "\n\n"
        return f"{text}{suffix}## {heading}\n\n{replacement}\n"
    start = match.end()
    next_match = re.search(r"^##\s+", text[start:], flags=re.MULTILINE)
    end = start + next_match.start() if next_match else len(text)
    return f"{text[:start]}\n\n{replacement.strip()}\n\n{text[end:].lstrip()}"


def update_topic_section(text: str, updates: dict[str, str]) -> str:
    section = parse_markdown_section(text, "选题判断")
    if not section:
        return text
    lines = section.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if "topic_angle" in updates and stripped.startswith("- 选题角度："):
            lines[index] = f"- 选题角度：{updates['topic_angle']}"
        if "opening_hook" in updates and stripped.startswith("- 开场钩子："):
            lines[index] = f"- 开场钩子：{updates['opening_hook']}"
    return replace_markdown_section(text, "选题判断", "\n".join(lines))


def clean_body_for_event(body: str) -> str:
    text = body
    for marker in ["【背景补全】", "【讨论任务】"]:
        if marker in text:
            text = text.split(marker, 1)[0]
    return text.strip()


def parse_comment_lines(text: str) -> list[str]:
    comments: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped == "未提取到可见评论。":
            continue
        if re.match(r"^\d+\.\s+", stripped) or stripped.startswith("- "):
            comments.append(re.sub(r"^\d+\.\s+|^-\s+", "", stripped))
    return comments


def extract_section(text: str, start_marker: str, end_marker: str | None) -> str:
    start = text.find(start_marker)
    if start == -1:
        return ""
    start += len(start_marker)
    if end_marker is None:
        return text[start:].strip()
    end = text.find(end_marker, start)
    if end == -1:
        return text[start:].strip()
    return text[start:end].strip()


def render_source_from_metadata(metadata: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"平台：{metadata.get('platform') or '未知'}",
            f"链接：{metadata.get('source_url') or '无'}",
            f"标题：{metadata.get('title') or '未提取到标题'}",
            f"作者：{metadata.get('author') or '未提取到作者'}",
            f"提取时间：{metadata.get('extracted_at') or '未知'}",
        ]
    )


def render_topic_brief_from_metadata(metadata: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"- 选题角度：{metadata.get('topic_angle') or '待判断'}",
            f"- 开场钩子：{metadata.get('opening_hook') or '待生成'}",
        ]
    )


def render_background(background: Any) -> str:
    if not isinstance(background, dict) or not background:
        return "无背景补全。"
    source_lines = "\n".join(
        f"- {item.get('title', '未命名来源')}：{item.get('url', '')}"
        for item in background.get("sources", [])
        if isinstance(item, dict)
    ) or "- 无可用来源。"
    error = f"\n\n错误：{background.get('error')}" if background.get("error") else ""
    return (
        f"- 触发原因：{background.get('reason') or '未知'}\n"
        f"- 检索词：{background.get('query') or '无'}\n\n"
        f"摘要：\n{background.get('summary') or '无'}\n\n"
        f"来源：\n{source_lines}"
        f"{error}"
    )


def build_event_brief(normalized: NormalizedInput) -> dict[str, Any]:
    body = extract_section(normalized.content, "【正文】", "【可见评论】") or normalized.content
    comments = normalized.comments or []
    title = normalized.title or default_title(normalized)
    conflict_points = infer_conflict_points(body, comments)
    comment_camps = infer_comment_camps(comments)
    topic_angle = normalized.metadata.get("topic_angle") or infer_topic_angle(title, body)
    opening_hook = normalized.metadata.get("opening_hook") or infer_opening_hook(title, conflict_points)
    return {
        "topic_angle": topic_angle,
        "opening_hook": opening_hook,
        "conflict_points": conflict_points,
        "comment_camps": comment_camps,
    }


def infer_topic_angle(title: str, body: str) -> str:
    text = f"{title}\n{body}"
    if any(term in text for term in ["创业", "产品", "商业", "用户", "增长"]):
        return "把个体选择放到成本、验证和增长逻辑里讨论。"
    if any(term in text for term in ["AI", "人工智能", "程序员", "技术", "芯片", "半导体"]):
        return "围绕技术变化对个人、产业和组织的影响展开。"
    if any(term in text for term in ["感情", "对象", "婚姻", "亲密关系", "边界"]):
        return "从关系边界、情绪需求和现实代价切入。"
    if any(term in text for term in ["政策", "公司", "制裁", "产业", "社会"]):
        return "从结构性变化、利益冲突和行动空间切入。"
    return "从事件表层争议进入真实动机、矛盾和可行动选择。"


def infer_opening_hook(title: str, conflict_points: list[str]) -> str:
    if conflict_points:
        return f"这件事表面在聊「{title}」，真正吵的是：{conflict_points[0]}"
    return f"这件事表面在聊「{title}」，真正值得拆的是背后的矛盾。"


def infer_conflict_points(body: str, comments: list[str]) -> list[str]:
    text = "\n".join([body, *comments])
    points: list[str] = []
    if any(term in text for term in ["该不该", "要不要", "能不能", "是否"]):
        points.append("选择本身的收益、风险和时机判断。")
    if any(term in text for term in ["评论", "骂", "支持", "反对", "争议"]):
        points.append("评论区支持与反对阵营对事实和价值的不同理解。")
    if any(term in text for term in ["成本", "风险", "钱", "收入", "失业", "裁员"]):
        points.append("理想判断与现实成本之间的冲突。")
    if any(term in text for term in ["家庭", "责任", "对象", "朋友", "同事"]):
        points.append("个人意愿与关系责任之间的拉扯。")
    if not points:
        points.append("事实判断、情绪立场和行动建议之间的分歧。")
    return points[:4]


def infer_comment_camps(comments: list[str]) -> list[str]:
    if not comments:
        return ["暂未提取到评论区阵营。"]
    joined = "\n".join(comments)
    camps: list[str] = []
    if any(term in joined for term in ["支持", "赞同", "可以", "应该", "冲"]):
        camps.append("支持派：更看重机会、情绪释放或价值表达。")
    if any(term in joined for term in ["反对", "不该", "别", "风险", "不建议"]):
        camps.append("谨慎派：更看重风险、成本和后果。")
    if any(term in joined for term in ["哈哈", "离谱", "抽象", "绷不住", "乐"]):
        camps.append("围观吐槽派：把事件当作情绪出口和梗素材。")
    if not camps:
        camps.append("观点混合派：评论区态度尚未形成清晰阵营。")
    return camps[:4]


def default_discussion_task() -> str:
    return (
        "请围绕以上社交媒体内容进行多人物视角讨论：判断核心事件、情绪动机、"
        "评论区分歧、潜在风险，并给出可行动建议。"
    )


def default_title(normalized: NormalizedInput) -> str:
    if normalized.source_url:
        return normalized.source_url
    return normalized.raw_input[:40] or "未命名事件"


def quote_meta(value: object) -> str:
    text = str(value or "")
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def unquote_meta(value: str) -> str:
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        value = value[1:-1]
    return value.replace('\\"', '"').replace("\\\\", "\\")


def slugify(text: str) -> str:
    normalized = re.sub(r"\s+", "-", text.strip())
    normalized = re.sub(r"[^\w\-\u4e00-\u9fff]+", "", normalized)
    normalized = normalized.strip("-_")
    return normalized[:36] or "event"
