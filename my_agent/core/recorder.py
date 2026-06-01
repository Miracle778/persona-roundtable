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
    color_map = build_agent_color_map(run)
    agent_items = "\n".join(
        f"""
        <article class="cast-card" style="--agent-color: {color_map[selection.skill.id]}">
          <div class="avatar">{escape(avatar_text(selection.skill.display_name))}</div>
          <div>
            <h3>{escape(selection.skill.display_name)}</h3>
            <p>{escape(" / ".join(selection.skill.categories) or "未分类")}</p>
            <small>匹配分 {selection.score} · {escape("、".join(selection.matched_terms) or "默认入选")}</small>
          </div>
        </article>
        """
        for selection in run.selected_agents
    )

    agent_id_to_name = {
        selection.skill.id: selection.skill.display_name
        for selection in run.selected_agents
    }
    for item in run.utterances:
        agent_id_to_name.setdefault(item.agent_id, item.agent_name)

    round_parts: list[str] = []
    step_index = 0
    for round_index, items in group_utterances_by_round(run).items():
        block, step_index = render_round_block(round_index, items, color_map, agent_id_to_name, step_index)
        round_parts.append(block)
    round_blocks = "\n".join(round_parts)
    source = format_source(run)
    input_title = run.input.title or ("手动输入问题" if run.input.type == "text" else "链接内容")
    total_rounds = max((item.round_index for item in run.utterances), default=0)
    page_label = "本期欢乐圆桌" if run.style == "show" else "本期圆桌讨论"
    mode_label = "节目模式" if run.style == "show" else "分析模式"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Discussion {escape(run.run_id)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f5f6f7;
      --panel: #ffffff;
      --text: #202124;
      --muted: #6b6f76;
      --line: #dce1e6;
      --soft-line: #eef1f3;
      --accent: #0f766e;
      --accent-2: #c2410c;
      --ink: #111827;
      --stage: #2f3a3f;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.62;
    }}
    main {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 28px 20px 56px;
    }}
    h1 {{ margin: 0; font-size: clamp(28px, 4vw, 48px); letter-spacing: 0; line-height: 1.08; }}
    h2 {{ margin: 30px 0 14px; font-size: 20px; letter-spacing: 0; }}
    h3 {{ letter-spacing: 0; }}
    .stage-header {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 18px;
      align-items: end;
      padding: 26px 0 18px;
      border-bottom: 1px solid var(--line);
    }}
    .mode-pill {{
      display: inline-flex;
      width: fit-content;
      margin-top: 12px;
      padding: 4px 10px;
      border-radius: 999px;
      background: #fff5ed;
      color: var(--accent-2);
      font-size: 13px;
      font-weight: 800;
    }}
    .eyebrow {{
      margin: 0 0 8px;
      color: var(--accent);
      font-size: 13px;
      font-weight: 800;
      text-transform: uppercase;
    }}
    .subtitle {{ margin: 12px 0 0; color: var(--muted); max-width: 760px; }}
    .run-badge {{
      display: grid;
      gap: 4px;
      min-width: 220px;
      padding: 12px 14px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    .run-badge span {{ color: var(--muted); font-size: 13px; }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin: 18px 0 6px;
    }}
    .metric {{
      padding: 13px 14px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    .metric strong {{ display: block; font-size: 22px; color: var(--ink); }}
    .metric span {{ color: var(--muted); font-size: 13px; }}
    .source-panel, .summary {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
    }}
    .source-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(220px, 320px);
      gap: 16px;
      align-items: start;
    }}
    .source-panel h3 {{ margin: 0 0 8px; font-size: 18px; }}
    .source-meta {{
      display: grid;
      gap: 8px;
      color: var(--muted);
      font-size: 13px;
    }}
    details {{
      margin-top: 12px;
      padding-top: 12px;
      border-top: 1px solid var(--soft-line);
    }}
    summary {{ cursor: pointer; font-weight: 700; color: var(--accent); }}
    .input-preview {{
      max-height: 320px;
      overflow: auto;
      padding-right: 8px;
    }}
    .chips {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }}
    .chip {{
      padding: 4px 9px;
      border-radius: 999px;
      background: #e6f3f1;
      color: var(--accent);
      font-size: 13px;
    }}
    .cast-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
    }}
    .cast-card {{
      display: flex;
      gap: 12px;
      min-height: 118px;
      padding: 14px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-left: 5px solid var(--agent-color);
      border-radius: 8px;
    }}
    .avatar {{
      flex: 0 0 44px;
      width: 44px;
      height: 44px;
      display: grid;
      place-items: center;
      border-radius: 50%;
      color: #fff;
      background: var(--agent-color);
      font-weight: 800;
    }}
    .cast-card h3 {{ margin: 1px 0 5px; font-size: 17px; }}
    .cast-card p {{ margin: 0 0 8px; color: var(--muted); font-size: 13px; }}
    .cast-card small {{ color: var(--muted); }}
    .timeline {{
      position: relative;
      display: grid;
      gap: 18px;
    }}
    .player {{
      position: sticky;
      top: 0;
      z-index: 5;
      display: grid;
      grid-template-columns: auto auto auto minmax(120px, 1fr);
      gap: 10px;
      align-items: center;
      margin: 0 0 14px;
      padding: 10px;
      background: rgba(245, 246, 247, 0.92);
      backdrop-filter: blur(12px);
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    .player button {{
      min-height: 36px;
      padding: 0 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      color: var(--ink);
      font-weight: 800;
      cursor: pointer;
    }}
    .player button.primary {{
      background: var(--accent);
      color: #fff;
      border-color: var(--accent);
    }}
    .progress-track {{
      height: 8px;
      border-radius: 999px;
      background: #d8dee3;
      overflow: hidden;
    }}
    .progress-fill {{
      width: 0%;
      height: 100%;
      background: var(--accent);
      transition: width 260ms ease;
    }}
    .round-block {{
      display: grid;
      grid-template-columns: 112px minmax(0, 1fr);
      gap: 18px;
      align-items: start;
    }}
    .round-label {{
      position: sticky;
      top: 12px;
      padding: 10px 10px;
      background: var(--stage);
      color: #fff;
      border-radius: 8px;
      text-align: center;
      font-weight: 800;
    }}
    .round-label span {{
      display: block;
      margin-top: 2px;
      font-size: 13px;
      font-weight: 500;
      opacity: 0.82;
    }}
    .round-stream {{ display: grid; gap: 12px; }}
    .utterance {{
      position: relative;
      display: grid;
      grid-template-columns: 52px minmax(0, 1fr);
      gap: 12px;
      padding: 16px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: 0 8px 24px rgba(17, 24, 39, 0.04);
      opacity: 0.58;
      transform: translateY(6px);
      transition: opacity 260ms ease, transform 260ms ease, box-shadow 260ms ease, border-color 260ms ease;
    }}
    .utterance.is-seen {{ opacity: 0.92; transform: translateY(0); }}
    .utterance.is-active {{
      opacity: 1;
      transform: translateY(0);
      border-color: var(--agent-color);
      box-shadow: 0 16px 42px rgba(17, 24, 39, 0.14);
    }}
    .utterance.is-active .avatar {{
      animation: pulseAvatar 900ms ease;
    }}
    @keyframes pulseAvatar {{
      0% {{ transform: scale(0.96); }}
      45% {{ transform: scale(1.08); }}
      100% {{ transform: scale(1); }}
    }}
    .utterance::before {{
      content: "";
      position: absolute;
      left: -1px;
      top: 0;
      bottom: 0;
      width: 5px;
      background: var(--agent-color);
      border-radius: 8px 0 0 8px;
    }}
    .utterance-head {{
      display: flex;
      gap: 8px;
      align-items: baseline;
      flex-wrap: wrap;
      margin-bottom: 8px;
    }}
    .speaker {{ font-size: 17px; }}
    .reply {{
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 2px 8px;
      border-radius: 999px;
      background: #fff5ed;
      color: var(--accent-2);
      font-size: 12px;
      font-weight: 700;
    }}
    .tags {{ color: var(--muted); font-size: 13px; }}
    time {{ color: var(--muted); font-size: 12px; }}
    .summary {{
      border-top: 6px solid var(--accent);
      box-shadow: 0 8px 24px rgba(17, 24, 39, 0.04);
    }}
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
      .stage-header, .source-grid, .round-block {{ grid-template-columns: 1fr; }}
      .metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .round-label {{ position: static; text-align: left; }}
      .utterance {{ grid-template-columns: 44px minmax(0, 1fr); }}
      .player {{ grid-template-columns: repeat(3, auto); }}
      .progress-track {{ grid-column: 1 / -1; }}
    }}
  </style>
</head>
<body>
  <main>
    <header class="stage-header">
      <div>
        <p class="eyebrow">Multi-Agent Roundtable</p>
        <h1>{escape(page_label)}</h1>
        <p class="subtitle">{escape(input_title)}</p>
        <span class="mode-pill">{escape(mode_label)}</span>
      </div>
      <aside class="run-badge">
        <strong>{escape(run.run_id)}</strong>
        <span>{escape(run.created_at)}</span>
        <span>{escape(source)}</span>
      </aside>
    </header>

    <section class="metrics">
      <div class="metric"><strong>{len(run.selected_agents)}</strong><span>参与人物</span></div>
      <div class="metric"><strong>{total_rounds}</strong><span>讨论轮次</span></div>
      <div class="metric"><strong>{len(run.utterances)}</strong><span>公开发言</span></div>
      <div class="metric"><strong>{len(run.input.comments)}</strong><span>可见评论</span></div>
    </section>

    <h2>议题素材</h2>
    <section class="source-panel">
      <div class="source-grid">
        <div>
          <h3>{escape(input_title)}</h3>
          <div class="chips">{''.join(f'<span class="chip">{escape(c)}</span>' for c in run.detected_categories)}</div>
        </div>
        <div class="source-meta">
          <span>来源：{escape(source)}</span>
          <span>作者：{escape(run.input.author or "未提取")}</span>
          <span>类型：{escape(run.input.type)}</span>
        </div>
      </div>
      <details>
        <summary>展开完整输入内容</summary>
        <div class="input-preview markdown-body">{render_markdown(run.input.content)}</div>
      </details>
    </section>

    <h2>角色阵容</h2>
    <section class="cast-grid">{agent_items}</section>

    <h2>讨论过程</h2>
    <section class="player" aria-label="讨论播放控制">
      <button class="primary" id="playToggle" type="button">播放</button>
      <button id="nextStep" type="button">下一条</button>
      <button id="resetSteps" type="button">重置</button>
      <div class="progress-track"><div class="progress-fill" id="progressFill"></div></div>
    </section>
    <section class="timeline">{round_blocks}</section>

    <h2>主持收场</h2>
    <section class="summary markdown-body">{render_markdown(run.summary)}</section>
  </main>
  <script>
    (() => {{
      const cards = Array.from(document.querySelectorAll("[data-step]"));
      const playButton = document.getElementById("playToggle");
      const nextButton = document.getElementById("nextStep");
      const resetButton = document.getElementById("resetSteps");
      const progressFill = document.getElementById("progressFill");
      let index = -1;
      let timer = null;

      function updateProgress() {{
        const value = cards.length ? Math.max(0, index + 1) / cards.length * 100 : 0;
        progressFill.style.width = value + "%";
      }}

      function activate(nextIndex, shouldScroll = true) {{
        if (!cards.length) return;
        index = Math.max(0, Math.min(nextIndex, cards.length - 1));
        cards.forEach((card, cardIndex) => {{
          card.classList.toggle("is-active", cardIndex === index);
          card.classList.toggle("is-seen", cardIndex <= index);
        }});
        updateProgress();
        if (shouldScroll) {{
          cards[index].scrollIntoView({{ behavior: "smooth", block: "center" }});
        }}
      }}

      function stop() {{
        if (timer) window.clearInterval(timer);
        timer = null;
        playButton.textContent = "播放";
      }}

      function play() {{
        if (timer) {{
          stop();
          return;
        }}
        playButton.textContent = "暂停";
        if (index < 0) activate(0);
        timer = window.setInterval(() => {{
          if (index >= cards.length - 1) {{
            stop();
            return;
          }}
          activate(index + 1);
        }}, 2600);
      }}

      playButton.addEventListener("click", play);
      nextButton.addEventListener("click", () => {{
        stop();
        activate(index + 1);
      }});
      resetButton.addEventListener("click", () => {{
        stop();
        index = -1;
        cards.forEach(card => card.classList.remove("is-active", "is-seen"));
        updateProgress();
        window.scrollTo({{ top: 0, behavior: "smooth" }});
      }});
      updateProgress();
    }})();
  </script>
</body>
</html>
"""


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def build_agent_color_map(run: DiscussionRun) -> dict[str, str]:
    palette = [
        "#0f766e",
        "#c2410c",
        "#2563eb",
        "#16a34a",
        "#be123c",
        "#7c3aed",
        "#ca8a04",
        "#0891b2",
    ]
    result: dict[str, str] = {}
    for index, selection in enumerate(run.selected_agents):
        result[selection.skill.id] = palette[index % len(palette)]
    for item in run.utterances:
        result.setdefault(item.agent_id, palette[len(result) % len(palette)])
    return result


def avatar_text(name: str) -> str:
    compact = re.sub(r"\s+", "", name)
    if not compact:
        return "?"
    return compact[:2]


def group_utterances_by_round(run: DiscussionRun) -> dict[int, list]:
    grouped: dict[int, list] = {}
    for item in run.utterances:
        grouped.setdefault(item.round_index, []).append(item)
    return dict(sorted(grouped.items()))


def render_round_block(
    round_index: int,
    items: list,
    color_map: dict[str, str],
    agent_id_to_name: dict[str, str],
    start_step: int,
) -> tuple[str, int]:
    chunks: list[str] = []
    step = start_step
    for item in items:
        chunks.append(render_utterance(item, color_map, agent_id_to_name, step))
        step += 1
    utterances = "\n".join(chunks)
    return f"""
    <section class="round-block">
      <div class="round-label">Round {round_index}<span>{len(items)} 条发言</span></div>
      <div class="round-stream">{utterances}</div>
    </section>
    """, step


def render_utterance(item, color_map: dict[str, str], agent_id_to_name: dict[str, str], step: int) -> str:
    reply_names = [
        agent_id_to_name.get(agent_id, agent_id)
        for agent_id in item.reply_to
        if agent_id != item.agent_id
    ]
    reply_text = "、".join(dict.fromkeys(reply_names))
    reply_badge = f'<span class="reply">接话：{escape(reply_text)}</span>' if reply_text else ""
    return f"""
    <article class="utterance" data-step="{step}" style="--agent-color: {color_map.get(item.agent_id, "#0f766e")}">
      <div class="avatar">{escape(avatar_text(item.agent_name))}</div>
      <div>
        <header class="utterance-head">
          <strong class="speaker">{escape(item.agent_name)}</strong>
          {reply_badge}
          <span class="tags">{escape(" / ".join(item.categories))}</span>
          <time>{escape(item.created_at)}</time>
        </header>
        <div class="markdown-body">{render_markdown(item.content)}</div>
      </div>
    </article>
    """


def format_source(run: DiscussionRun) -> str:
    if run.input.type == "text":
        return "手动输入"
    platform = run.input.platform or "URL"
    if run.input.source_url:
        return f"{platform}：{run.input.source_url}"
    return platform


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
