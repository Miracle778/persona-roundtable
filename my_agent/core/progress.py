from __future__ import annotations

import sys
from collections.abc import Callable


ProgressCallback = Callable[[str], None]


def noop_progress(message: str) -> None:
    return None


def stderr_progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)
