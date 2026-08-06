#!/usr/bin/env python3
"""Quick-Tunnel scanner benchmark runner skeleton."""

from __future__ import annotations

import json
import time
from pathlib import Path


def measure(function, *args, **kwargs):
    start = time.perf_counter()
    result = function(*args, **kwargs)
    elapsed = time.perf_counter() - start
    return result, elapsed


def write_report(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


if __name__ == "__main__":
    write_report(
        Path("benchmark/reports/benchmark-result.json"),
        {
            "status": "initialized",
            "scanner": "baseline",
            "metrics": {},
        },
    )
