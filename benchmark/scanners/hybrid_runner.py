"""Hybrid scanner benchmark adapter."""

from __future__ import annotations

import time
from pathlib import Path

from .hybrid import scan_path


def run(root: str) -> dict:
    start = time.perf_counter()
    result = scan_path(Path(root))
    elapsed = time.perf_counter() - start
    result["duration_seconds"] = elapsed
    result["throughput_mb_s"] = (
        result.get("bytes_scanned", 0) / 1024 / 1024 / elapsed
        if elapsed
        else 0
    )
    return result
