"""Run benchmark comparison between scanner implementations."""

from __future__ import annotations

import json
from pathlib import Path

from scanners import baseline_runner, hybrid_runner


def compare(root: str) -> dict:
    return {
        "baseline": baseline_runner.run(root),
        "hybrid": hybrid_runner.run(root),
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("--output", default="benchmark-result.json")
    args = parser.parse_args()

    result = compare(args.path)
    Path(args.output).write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )
