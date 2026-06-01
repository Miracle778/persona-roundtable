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
    frontmatter = {
        "my_agent_event_version": EVENT_VERSION,
        "event_type": source_type,
        "platform": normalized.platform or "",
        "source_url": normalized.source_url or "",
        "title": normalized.title or "",
        "author": normalized.author or "",
        "extracted_at": str(extracted_at),
    }
    body = extract_section(normalized.content, "【正文】", "【可见评论】") or normalized.content
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
            "## 原帖正文",
            "",
            body.strip() or "未提取到正文。",
            "",
            "## 评论区摘录",
            "",
            render_comments(comments, comment_threads),
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


def build_content_from_event_markdown(content_text: str, metadata: dict[str, Any]) -> str:
    source = parse_markdown_section(content_text, "事件来源")
    body = parse_markdown_section(content_text, "原帖正文")
    comments = parse_markdown_section(content_text, "评论区摘录")
    task = parse_markdown_section(content_text, "讨论任务") or default_discussion_task()
    return "\n".join(
        [
            "【内容来源】",
            source.strip() or render_source_from_metadata(metadata),
            "",
            "【正文】",
            body.strip() or "未提取到正文。",
            "",
            "【可见评论】",
            comments.strip() or "未提取到可见评论。",
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
