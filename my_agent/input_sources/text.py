from __future__ import annotations

from my_agent.core.models import NormalizedInput
from my_agent.core.progress import ProgressCallback, noop_progress
from my_agent.input_sources.base import InputSource


class TextInputSource(InputSource):
    def normalize(
        self,
        raw_input: str,
        progress: ProgressCallback = noop_progress,
    ) -> NormalizedInput:
        progress("[3/8] 检测到手输文本，正在整理讨论输入...")
        content = raw_input.strip()
        return NormalizedInput(
            type="text",
            raw_input=raw_input,
            content=content,
            metadata={"source": "manual_text"},
        )
