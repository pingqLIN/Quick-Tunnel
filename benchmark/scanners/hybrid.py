"""Hybrid risk based scanner prototype.

Phase 1 keeps this isolated from production. The benchmark compares the
pipeline before any production replacement decision.
"""

from pathlib import Path


HIGH_RISK_NAMES = {
    '.env',
    'credentials.json',
    'secrets.yaml',
    'private.key',
}


def calculate_risk(path: Path) -> int:
    score = 0
    if path.name.lower() in HIGH_RISK_NAMES:
        score += 50
    if any(token in path.name.lower() for token in ('secret', 'token', 'password')):
        score += 20
    return score


def should_deep_scan(path: Path) -> bool:
    return calculate_risk(path) >= 50
