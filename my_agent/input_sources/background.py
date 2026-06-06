from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import replace
from datetime import datetime
from typing import Any

from my_agent.core.models import BackgroundContext, NormalizedInput
from my_agent.core.progress import ProgressCallback, noop_progress


WebSearchMode = str

REALTIME_TERMS = [
    "最新",
    "最近",
    "今天",
    "昨天",
    "热搜",
    "刚刚",
    "现在",
    "2026",
    "政策",
    "公司",
    "裁员",
    "产品发布",
    "发布会",
    "上市",
    "制裁",
]

EXPLICIT_SEARCH_TERMS = [
    "帮我查背景",
    "结合最新信息",
    "看看网上怎么说",
    "查一下",
    "搜一下",
]


def maybe_enrich_background(
    normalized: NormalizedInput,
    mode: WebSearchMode = "auto",
    progress: ProgressCallback = noop_progress,
) -> NormalizedInput:
    if mode == "off":
        return normalized
    should_search, reason = should_enrich(normalized)
    if mode == "on":
        should_search = True
        reason = reason or "用户显式开启 web search。"
    if not should_search:
        return normalized

    query = build_search_query(normalized)
    progress(f"[3/8] 正在补全背景：{reason}")
    try:
        results = search_web(query)
        summary = summarize_results(query, results)
        background = BackgroundContext(
            mode=mode,
            triggered=True,
            reason=reason,
            query=query,
            summary=summary,
            sources=results,
        )
        progress(f"[3/8] 背景补全完成：{len(results)} 个来源。")
    except Exception as exc:
        background = BackgroundContext(
            mode=mode,
            triggered=True,
            reason=reason,
            query=query,
            summary="背景补全失败，讨论将只基于用户输入和已提取内容进行。",
            sources=[],
            error=str(exc),
        )
        progress(f"[3/8] 背景补全失败，已保留失败信息：{exc}")

    return attach_background(normalized, background)


def should_enrich(normalized: NormalizedInput) -> tuple[bool, str]:
    raw = normalized.raw_input.strip()
    content = normalized.content.strip()
    lower_text = f"{raw}\n{content}".lower()
    if any(term.lower() in lower_text for term in EXPLICIT_SEARCH_TERMS):
        return True, "用户显式要求查背景。"
    if any(term.lower() in lower_text for term in REALTIME_TERMS):
        return True, "输入包含近期/实时事件线索。"
    plain = re.sub(r"https?://\S+", "", content)
    if len(plain) < 80 and not looks_like_personal_question(plain):
        return True, "输入较短，可能缺少讨论背景。"
    if normalized.type == "url":
        body = extract_between(content, "【正文】", "【可见评论】") or content
        if len(body.strip()) < 240 or len(normalized.comments) < 2:
            return True, "链接提取正文或评论较少。"
    return False, ""


def looks_like_personal_question(text: str) -> bool:
    personal_terms = ["我", "对象", "男朋友", "女朋友", "老婆", "老公", "同事", "朋友", "家里"]
    advice_terms = ["怎么办", "该不该", "要不要", "怎么选"]
    return any(term in text for term in personal_terms) and any(term in text for term in advice_terms)


def build_search_query(normalized: NormalizedInput) -> str:
    if normalized.title:
        return normalized.title
    raw = normalized.raw_input.strip()
    if raw and not raw.startswith("http"):
        return compact_query(raw)
    body = extract_between(normalized.content, "【正文】", "【可见评论】") or normalized.content
    return compact_query(body)


def search_web(query: str, limit: int = 5) -> list[dict[str, Any]]:
    encoded = urllib.parse.urlencode({"q": query})
    url = f"https://duckduckgo.com/html/?{encoded}"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 my_agent background context",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            html = response.read().decode("utf-8", errors="ignore")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"web search 请求失败：{exc}") from exc
    results = parse_duckduckgo_html(html, limit=limit)
    if not results:
        raise RuntimeError("web search 没有返回可解析结果。")
    return results


def parse_duckduckgo_html(page: str, limit: int = 5) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    pattern = re.compile(
        r'<a[^>]+class="result__a"[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
        flags=re.IGNORECASE | re.DOTALL,
    )
    snippets = re.findall(
        r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>|<div[^>]+class="result__snippet"[^>]*>(.*?)</div>',
        page,
        flags=re.IGNORECASE | re.DOTALL,
    )
    snippet_texts = [clean_html(a or b) for a, b in snippets]
    for index, match in enumerate(pattern.finditer(page)):
        title = clean_html(match.group("title"))
        href = clean_url(match.group("href"))
        if not title or not href:
            continue
        results.append(
            {
                "title": title,
                "url": href,
                "snippet": snippet_texts[index] if index < len(snippet_texts) else "",
                "retrieved_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            }
        )
        if len(results) >= limit:
            break
    return results


def summarize_results(query: str, results: list[dict[str, Any]]) -> str:
    if not results:
        return "未检索到可用背景。"
    lines = [
        f"围绕「{query}」检索到 {len(results)} 条背景线索。以下内容仅作为讨论素材，仍需结合原始链接和用户问题判断："
    ]
    for index, item in enumerate(results, start=1):
        snippet = item.get("snippet") or "无摘要。"
        lines.append(f"{index}. {item.get('title', '未命名来源')}：{snippet}")
    return "\n".join(lines)


def attach_background(normalized: NormalizedInput, background: BackgroundContext) -> NormalizedInput:
    block = render_background_block(background)
    content = normalized.content
    if "【背景补全】" not in content:
        content = f"{content.rstrip()}\n\n{block}"
    return replace(
        normalized,
        content=content,
        background=background,
        metadata={
            **normalized.metadata,
            "background_context": background_to_dict(background),
        },
    )


def render_background_block(background: BackgroundContext) -> str:
    source_lines = "\n".join(
        f"- {item.get('title', '未命名来源')}：{item.get('url', '')}"
        for item in background.sources
    ) or "- 无可用来源。"
    error_line = f"\n错误：{background.error}" if background.error else ""
    return (
        "【背景补全】\n"
        f"触发原因：{background.reason}\n"
        f"检索词：{background.query}\n"
        f"摘要：\n{background.summary}\n\n"
        f"来源：\n{source_lines}"
        f"{error_line}"
    )


def background_to_dict(background: BackgroundContext) -> dict[str, Any]:
    return {
        "mode": background.mode,
        "triggered": background.triggered,
        "reason": background.reason,
        "query": background.query,
        "summary": background.summary,
        "sources": background.sources,
        "error": background.error,
    }


def clean_html(value: str) -> str:
    text = re.sub(r"<.*?>", "", value)
    text = urllib.parse.unquote(text)
    text = (
        text.replace("&amp;", "&")
        .replace("&quot;", '"')
        .replace("&#x27;", "'")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )
    return " ".join(text.split())


def clean_url(value: str) -> str:
    text = value.replace("&amp;", "&")
    parsed = urllib.parse.urlparse(text)
    if parsed.netloc == "duckduckgo.com" and parsed.path.startswith("/l/"):
        query = urllib.parse.parse_qs(parsed.query)
        if query.get("uddg"):
            return query["uddg"][0]
    return text


def compact_query(text: str, limit: int = 80) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit].rstrip("，。！？,.!? ")


def extract_between(text: str, start_marker: str, end_marker: str) -> str:
    start = text.find(start_marker)
    if start == -1:
        return ""
    start += len(start_marker)
    end = text.find(end_marker, start)
    if end == -1:
        return text[start:].strip()
    return text[start:end].strip()
