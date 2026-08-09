"""Adapter that benchmarks the current macOS production scanner unchanged."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

DEFAULT_MAX_FILE_BYTES = 25 * 1024 * 1024


def load_production_module(repo_root: Path) -> ModuleType:
    module_path = repo_root / "macos" / "share-codex-review.py"
    module_name = "quick_tunnel_production_scanner"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load production scanner: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def scan_path(
    root: Path,
    *,
    repo_root: Path | None = None,
    maximum_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
) -> dict[str, Any]:
    repository = repo_root or Path(__file__).resolve().parents[2]
    production = load_production_module(repository)

    inventory = production.build_inventory(
        root,
        maximum_file_bytes,
        additional_excludes=(),
    )
    detections = production.find_potential_secret_paths(inventory.files)

    logical_bytes = sum(entry.length for entry in inventory.files)
    secret_scan_bytes = sum(
        entry.length
        for entry in inventory.files
        if entry.source_path.suffix.lower() in production.TEXT_FILE_EXTENSIONS
        and entry.length <= 2 * 1024 * 1024
    )

    return {
        "scanner": "production-baseline",
        "files_considered": len(inventory.files),
        "logical_bytes": logical_bytes,
        "estimated_physical_bytes_read": logical_bytes + secret_scan_bytes,
        "excluded_count": inventory.excluded_count,
        "oversized_count": inventory.oversized_count,
        "detections": list(detections),
    }
