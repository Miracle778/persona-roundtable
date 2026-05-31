from __future__ import annotations

from urllib.parse import urlparse

from my_agent.core.progress import ProgressCallback, noop_progress
from my_agent.input_sources.text import TextInputSource
from my_agent.input_sources.url import UrlInputSource


def normalize_user_input(
    raw_input: str,
    progress: ProgressCallback = noop_progress,
):
    parsed = urlparse(raw_input.strip())
    progress("[2/8] 正在解析输入...")
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return UrlInputSource().normalize(raw_input, progress=progress)
    return TextInputSource().normalize(raw_input, progress=progress)
