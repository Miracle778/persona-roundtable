from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path

from my_agent.core.models import DiscussionRun


def build_run_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S-%f")


class DiscussionRecorder:
    def save(self, run: DiscussionRun) -> tuple[Path, Path]:
        run.output_dir.mkdir(parents=True, exist_ok=True)
        json_path = run.output_dir / "discussion.json"
        html_path = run.output_dir / "discussion.html"
        json_path.write_text(json.dumps(run.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        html_path.write_text(render_html(run), encoding="utf-8")
        return json_path, html_path


def render_html(run: DiscussionRun) -> str:
    agent_items = "\n".join(
        f"""
        <li>
          <strong>{escape(selection.skill.display_name)}</strong>
          <span>{escape(" / ".join(selection.skill.categories) or "未分类")}</span>
          <small>score {selection.score}; {escape("、".join(selection.matched_terms))}</small>
        </li>
        """
        for selection in run.selected_agents
    )
    utterance_items = "\n".join(
        f"""
        <article class="utterance">
          <header>
            <span class="round">Round {item.round_index}</span>
            <strong>{escape(item.agent_name)}</strong>
            <span class="tags">{escape(" / ".join(item.categories))}</span>
            <time>{escape(item.created_at)}</time>
          </header>
          <div class="markdown-body">{render_markdown(item.content)}</div>
        </article>
        """
        for item in run.utterances
    )
    source = "手动输入" if run.input.type == "text" else f"{run.input.platform or 'URL'}：{run.input.source_url}"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Discussion {escape(run.run_id)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f7f4;
      --panel: #ffffff;
      --text: #202124;
      --muted: #6b6f76;
      --line: #ddd8cc;
      --accent: #0f766e;
      --accent-2: #9a3412;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.65;
    }}
    main {{
      max-width: 1080px;
      margin: 0 auto;
      padding: 32px 20px 56px;
    }}
    h1 {{ margin: 0 0 8px; font-size: 28px; letter-spacing: 0; }}
    h2 {{ margin: 28px 0 12px; font-size: 18px; letter-spacing: 0; }}
    .meta, .summary, .question, .agents, .utterance {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    .meta {{ padding: 14px 16px; color: var(--muted); }}
    .question, .summary {{ padding: 18px; }}
    .chips {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }}
    .chip {{
      padding: 4px 9px;
      border-radius: 999px;
      background: #e6f3f1;
      color: var(--accent);
      font-size: 13px;
    }}
    .agents {{ list-style: none; padding: 8px 0; margin: 0; }}
    .agents li {{
      display: grid;
      grid-template-columns: minmax(120px, 220px) 1fr auto;
      gap: 12px;
      padding: 10px 14px;
      border-top: 1px solid var(--line);
      align-items: center;
    }}
    .agents li:first-child {{ border-top: 0; }}
    .agents span, .agents small, time {{ color: var(--muted); }}
    .timeline {{ display: grid; gap: 12px; }}
    .utterance {{ padding: 16px; }}
    .utterance header {{
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
      margin-bottom: 8px;
    }}
    .round {{
      color: var(--accent-2);
      font-weight: 700;
      font-size: 13px;
    }}
    .tags {{ color: var(--muted); font-size: 13px; }}
    .markdown-body h1,
    .markdown-body h2,
    .markdown-body h3 {{
      margin: 12px 0 8px;
      line-height: 1.35;
      letter-spacing: 0;
    }}
    .markdown-body h1 {{ font-size: 22px; }}
    .markdown-body h2 {{ font-size: 18px; }}
    .markdown-body h3 {{ font-size: 16px; }}
    .markdown-body p {{ margin: 8px 0; white-space: pre-wrap; }}
    .markdown-body p:first-child,
    .markdown-body h1:first-child,
    .markdown-body h2:first-child,
    .markdown-body h3:first-child {{ margin-top: 0; }}
    .markdown-body p:last-child,
    .markdown-body ul:last-child,
    .markdown-body ol:last-child {{ margin-bottom: 0; }}
    .markdown-body ul,
    .markdown-body ol {{ margin: 8px 0 8px 22px; padding: 0; }}
    .markdown-body li {{ margin: 4px 0; }}
    .markdown-body strong {{ font-weight: 700; }}
    .markdown-body code {{
      padding: 1px 5px;
      border-radius: 4px;
      background: #f1eee7;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 0.92em;
    }}
    @media (max-width: 720px) {{
      main {{ padding: 22px 12px 40px; }}
      .agents li {{ grid-template-columns: 1fr; gap: 2px; }}
    }}
  </style>
</head>
<body>
  <main>
    <h1>多人物视角讨论记录</h1>
    <div class="meta">Run: {escape(run.run_id)} · {escape(run.created_at)} · 来源：{escape(source)}</div>

    <h2>问题</h2>
    <section class="question">
      <p>{escape(run.input.content)}</p>
      <div class="chips">{''.join(f'<span class="chip">{escape(c)}</span>' for c in run.detected_categories)}</div>
    </section>

    <h2>参与人物</h2>
    <ul class="agents">{agent_items}</ul>

    <h2>讨论过程</h2>
    <section class="timeline">{utterance_items}</section>

    <h2>主持总结</h2>
    <section class="summary markdown-body">{render_markdown(run.summary)}</section>
  </main>
</body>
</html>
"""


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def render_markdown(text: object) -> str:
    lines = str(text).splitlines()
    blocks: list[str] = []
    paragraph: list[str] = []
    list_type: str | None = None
    list_items: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            content = " ".join(line.strip() for line in paragraph).strip()
            if content:
                blocks.append(f"<p>{render_inline_markdown(content)}</p>")
            paragraph = []

    def flush_list() -> None:
        nonlocal list_type, list_items
        if list_type and list_items:
            items = "".join(f"<li>{render_inline_markdown(item)}</li>" for item in list_items)
            blocks.append(f"<{list_type}>{items}</{list_type}>")
        list_type = None
        list_items = []

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            flush_list()
            continue

        heading = re.match(r"^(#{1,3})\s+(.+)$", stripped)
        if heading:
            flush_paragraph()
            flush_list()
            level = len(heading.group(1))
            blocks.append(f"<h{level}>{render_inline_markdown(heading.group(2))}</h{level}>")
            continue

        unordered = re.match(r"^[-*]\s+(.+)$", stripped)
        ordered = re.match(r"^\d+[.)]\s+(.+)$", stripped)
        if unordered or ordered:
            flush_paragraph()
            current_type = "ul" if unordered else "ol"
            if list_type and list_type != current_type:
                flush_list()
            list_type = current_type
            list_items.append((unordered or ordered).group(1))
            continue

        flush_list()
        paragraph.append(stripped)

    flush_paragraph()
    flush_list()
    return "\n".join(blocks)


def render_inline_markdown(text: str) -> str:
    escaped = escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    return escaped
