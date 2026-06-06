from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from my_agent.core.progress import ProgressCallback, noop_progress
from my_agent.input_sources.background import maybe_enrich_background
from my_agent.input_sources.event_markdown import load_discussion_event_markdown, save_discussion_event_markdown, with_event_markdown_path
from my_agent.input_sources.text import TextInputSource
from my_agent.input_sources.url import UrlInputSource


def normalize_user_input(
    raw_input: str,
    progress: ProgressCallback = noop_progress,
    event_dir: Path | None = None,
    web_search: str = "auto",
):
    stripped = raw_input.strip()
    event_path = maybe_event_markdown_path(stripped)
    progress("[2/8] 正在解析输入...")
    if event_path:
        normalized = load_discussion_event_markdown(event_path, progress=progress)
        return maybe_enrich_background(normalized, mode=web_search, progress=progress)
    parsed = urlparse(stripped)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        normalized = UrlInputSource(event_dir=None).normalize(raw_input, progress=progress)
        normalized = maybe_enrich_background(normalized, mode=web_search, progress=progress)
        if event_dir:
            path = save_discussion_event_markdown(normalized, event_dir, progress=progress)
            normalized = with_event_markdown_path(normalized, path)
        return normalized
    normalized = TextInputSource().normalize(raw_input, progress=progress)
    return maybe_enrich_background(normalized, mode=web_search, progress=progress)


def maybe_event_markdown_path(raw_input: str) -> Path | None:
    candidate = raw_input
    if candidate.startswith("@"):
        candidate = candidate[1:]
    if candidate.startswith("file://"):
        parsed = urlparse(candidate)
        candidate = parsed.path
    path = Path(candidate).expanduser()
    if path.suffix.lower() != ".md":
        return None
    if path.exists() and path.is_file():
        return path
    return None
