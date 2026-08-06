#!/usr/bin/env python3
"""Run the Quick-Tunnel scanner benchmark matrix.

This runner keeps baseline and hybrid measurements comparable by using the
same generated corpus and emitting a single JSON comparison artifact.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


def run_step(label: str, command: list[str]) -> dict[str, object]:
    started = time.perf_counter()
    completed = subprocess.run(command, capture_output=True, text=True)
    elapsed = time.perf_counter() - started
    return {
        "label": label,
        "command": command,
        "elapsed_seconds": round(elapsed, 6),
        "returncode": completed.returncode,
        "stdout": completed.stdout[-2000:],
        "stderr": completed.stderr[-2000:],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("benchmark/reports/comparison.json"))
    args = parser.parse_args()

    results = [
        run_step("baseline", [sys.executable, "-m", "benchmark.scanners.run_baseline"]),
        run_step("hybrid", [sys.executable, "-m", "benchmark.scanners.run_hybrid"]),
    ]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"schema_version": 1, "results": results}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
