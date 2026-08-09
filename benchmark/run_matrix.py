#!/usr/bin/env python3
"""Run the canonical Quick-Tunnel benchmark through a subprocess.

The canonical ``benchmark.runner`` owns corpus comparison and report schema.
This wrapper remains useful for automation that needs a subprocess boundary.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--corpus",
        type=Path,
        default=Path("benchmark/corpus/generated"),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("benchmark/corpus/generated/manifest.json"),
    )
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("benchmark/reports/benchmark-result.json"),
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=Path("benchmark/reports/QT-SCANNER-BENCHMARK-REPORT.md"),
    )
    args = parser.parse_args()

    command = [
        sys.executable,
        "-m",
        "benchmark.runner",
        "--corpus",
        str(args.corpus),
        "--manifest",
        str(args.manifest),
        "--repeats",
        str(args.repeats),
        "--warmups",
        str(args.warmups),
        "--json-output",
        str(args.output),
        "--markdown-output",
        str(args.markdown_output),
    ]
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
