#!/usr/bin/env python3
"""Generate a deterministic synthetic corpus for scanner benchmarks."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

SAFE_BAITS = (
    "ghp_EXAMPLE_NOT_A_REAL_TOKEN",
    "AKIAEXAMPLE",
    "sk-example-placeholder",
    "github_pat_example",
)

SECRET_VALUES = (
    "-----BEGIN PRIVATE KEY-----",
    "AKIA" + "A1B2C3D4E5F6G7H8",
    "ghp_" + "A" * 36,
    "github_pat_" + "B" * 40,
    "sk-proj-" + "C" * 40,
    "xoxb-" + "D" * 24,
    "AIza" + "E" * 35,
)


def _padded_text(prefix: str, payload_bytes: int) -> str:
    """Build the deterministic ASCII payload in O(n) time."""

    filler = (
        "\nThis is deterministic benchmark source text. "
        "It contains no live credential material."
    )
    if payload_bytes <= len(prefix):
        return prefix[:payload_bytes]
    remaining = payload_bytes - len(prefix)
    repeats = (remaining + len(filler) - 1) // len(filler)
    return (prefix + filler * repeats)[:payload_bytes]


def generate(
    root: Path,
    safe_files: int,
    secret_files: int,
    payload_bytes: int,
) -> dict[str, object]:
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    labels: dict[str, bool] = {}

    for index in range(safe_files):
        relative = Path("clean") / f"group_{index % 32:02d}" / f"file_{index:05d}.txt"
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        bait = SAFE_BAITS[index % len(SAFE_BAITS)]
        path.write_text(
            _padded_text(f"safe fixture {index}\n{bait}\n", payload_bytes),
            encoding="utf-8",
        )
        labels[relative.as_posix()] = False

    for index in range(secret_files):
        relative = Path("detected") / f"group_{index % 16:02d}" / f"fixture_{index:05d}.txt"
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        secret = SECRET_VALUES[index % len(SECRET_VALUES)]
        path.write_text(
            _padded_text(f"synthetic fixture\n{secret}\n", payload_bytes),
            encoding="utf-8",
        )
        labels[relative.as_posix()] = True

    utf16_relative = Path("detected") / "encoding_utf16.txt"
    utf16_path = root / utf16_relative
    utf16_path.parent.mkdir(parents=True, exist_ok=True)
    utf16_path.write_text(
        "synthetic fixture\n" + SECRET_VALUES[2] + "\n",
        encoding="utf-16",
    )
    labels[utf16_relative.as_posix()] = True

    malformed_relative = Path("detected") / "encoding_malformed_utf8.txt"
    malformed_path = root / malformed_relative
    malformed_path.write_bytes(
        b"prefix\xff" + SECRET_VALUES[3].encode("ascii") + b"\nsuffix"
    )
    labels[malformed_relative.as_posix()] = True

    binary_relative = Path("binary") / "payload.bin"
    binary_path = root / binary_relative
    binary_path.parent.mkdir(parents=True, exist_ok=True)
    binary_path.write_bytes(bytes(range(256)) * max(1, payload_bytes // 256))
    labels[binary_relative.as_posix()] = False

    excluded_paths = (
        Path(".env"),
        Path(".ssh") / "id_rsa",
        Path("node_modules") / "embedded_secret.txt",
    )
    for relative in excluded_paths:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(SECRET_VALUES[2], encoding="utf-8")

    manifest = {
        "schema_version": 1,
        "generator": {
            "safe_files": safe_files,
            "secret_files": secret_files,
            "payload_bytes": payload_bytes,
        },
        "labels": dict(sorted(labels.items())),
        "excluded_paths": [path.as_posix() for path in excluded_paths],
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("benchmark/corpus/generated"),
    )
    parser.add_argument("--safe-files", type=int, default=3000)
    parser.add_argument("--secret-files", type=int, default=120)
    parser.add_argument("--payload-bytes", type=int, default=16384)
    args = parser.parse_args()
    generate(
        args.root,
        safe_files=args.safe_files,
        secret_files=args.secret_files,
        payload_bytes=args.payload_bytes,
    )


if __name__ == "__main__":
    main()
