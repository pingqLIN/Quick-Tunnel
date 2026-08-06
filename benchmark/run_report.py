#!/usr/bin/env python3
"""Generate markdown comparison reports from benchmark JSON results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def render(data: dict) -> str:
    baseline = data.get("baseline", {})
    hybrid = data.get("hybrid", {})

    def row(name: str, key: str) -> str:
        return f"| {name} | {baseline.get(key, '-') } | {hybrid.get(key, '-')} |"

    return "\n".join([
        "# QT Scanner Comparison Report",
        "",
        "| Metric | Baseline | Hybrid |",
        "|---|---:|---:|",
        row("Files scanned", "files_scanned"),
        row("Bytes scanned", "bytes_scanned"),
        row("Duration seconds", "duration_seconds"),
        row("Throughput MB/s", "throughput_mb_s"),
        row("Detections", "detections"),
        "",
    ])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(render(json.loads(args.input.read_text())), encoding="utf-8")


if __name__ == "__main__":
    main()
