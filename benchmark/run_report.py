#!/usr/bin/env python3
"""Generate markdown comparison reports from benchmark JSON results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .runner import write_markdown


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    report = json.loads(args.input.read_text(encoding="utf-8"))
    write_markdown(args.output, report)


if __name__ == "__main__":
    main()
