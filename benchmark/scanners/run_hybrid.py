#!/usr/bin/env python3
"""Run the hybrid scanner benchmark adapter."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .hybrid import scan_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    start = time.perf_counter()
    result = scan_path(args.root)
    elapsed = time.perf_counter() - start

    result["duration_seconds"] = elapsed
    result["throughput_mb_s"] = (
        result.get("logical_bytes", 0) / 1024 / 1024 / elapsed
        if elapsed else 0
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
