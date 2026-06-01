from __future__ import annotations

from urllib.parse import urlparse
from pathlib import Path

from my_agent.core.models import NormalizedInput
from my_agent.core.progress import ProgressCallback, noop_progress
from my_agent.input_sources.base import InputSource
from my_agent.input_sources.event_markdown import save_discussion_event_markdown, with_event_markdown_path
from my_agent.input_sources.media_crawler import detect_platform, extract_social_url


class UrlInputSource(InputSource):
    """Reserved extension point for social/content platform extraction."""

    def __init__(self, event_dir: Path | None = None):
        self.event_dir = event_dir

    def normalize(
        self,
        raw_input: str,
        progress: ProgressCallback = noop_progress,
    ) -> NormalizedInput:
        parsed = urlparse(raw_input)
        platform = self._detect_platform(parsed.netloc)
        progress(f"[3/8] 检测到链接，平台：{platform or '未知'}。")
        if platform in {"zhihu", "weibo"}:
            normalized = extract_social_url(raw_input, progress=progress)
            if self.event_dir:
                path = save_discussion_event_markdown(normalized, self.event_dir, progress=progress)
                normalized = with_event_markdown_path(normalized, path)
            return normalized
        raise ValueError(f"暂不支持该平台的链接解析：{platform or raw_input}。第一版只支持知乎和微博。")

    @staticmethod
    def _detect_platform(host: str) -> str | None:
        return detect_platform(f"https://{host}")
