#!/usr/bin/env python3
"""Generate synthetic scanner benchmark corpus."""

from pathlib import Path


SAFE_FILES = 100
SECRET_FILES = 10


def generate(root: Path) -> None:
    safe = root / "clean"
    secrets = root / "secrets"
    safe.mkdir(parents=True, exist_ok=True)
    secrets.mkdir(parents=True, exist_ok=True)

    for index in range(SAFE_FILES):
        (safe / f"file_{index}.txt").write_text(
            "normal source text\n",
            encoding="utf-8",
        )

    for index in range(SECRET_FILES):
        (secrets / f"secret_{index}.txt").write_text(
            "github_pat_" + "A" * 40 + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    generate(Path("benchmark/corpus"))
