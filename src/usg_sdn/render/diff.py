"""Text diff helper for config comparison (running vs desired)."""
from __future__ import annotations

import difflib


def config_diff(running: str, desired: str, *, n: int = 3, fromfile: str = "running", tofile: str = "desired") -> str:
    return "".join(
        difflib.unified_diff(
            running.splitlines(keepends=True),
            desired.splitlines(keepends=True),
            fromfile=fromfile,
            tofile=tofile,
            n=n,
        )
    )
