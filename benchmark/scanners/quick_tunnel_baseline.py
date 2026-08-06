"""Benchmark adapter for the current Quick-Tunnel security pipeline.

This module intentionally mirrors the production filtering model without
modifying production code. It measures the current approach as a baseline.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

EXCLUDED_DIRS = {
    ".git", ".hg", ".svn", "node_modules", ".venv", "venv",
    ".ssh", ".aws", ".azure", ".gcloud"
}

EXCLUDED_FILES = (
    ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx",
    "credentials*.json", "secrets.*"
)

SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,255}"),
    re.compile(r"-----BEGIN .*PRIVATE KEY-----")
]


def excluded(path: Path) -> bool:
    if any(part in EXCLUDED_DIRS for part in path.parts):
        return True
    return any(path.match(pattern) for pattern in EXCLUDED_FILES)


def scan(root: Path) -> dict:
    files = 0
    bytes_scanned = 0
    detections = 0

    for path in root.rglob("*"):
        if not path.is_file() or excluded(path):
            continue

        files += 1
        data = path.read_bytes()
        bytes_scanned += len(data)

        digest = hashlib.sha256(data).hexdigest()
        _ = digest

        try:
            text = data.decode("utf-8", errors="ignore")
        except Exception:
            continue

        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                detections += 1
                break

    return {
        "files_scanned": files,
        "bytes_scanned": bytes_scanned,
        "detections": detections,
    }
