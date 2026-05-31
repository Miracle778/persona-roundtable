from __future__ import annotations

from abc import ABC, abstractmethod

from my_agent.core.models import NormalizedInput
from my_agent.core.progress import ProgressCallback, noop_progress


class InputSource(ABC):
    @abstractmethod
    def normalize(
        self,
        raw_input: str,
        progress: ProgressCallback = noop_progress,
    ) -> NormalizedInput:
        """Convert a raw user input into content consumed by agents."""
