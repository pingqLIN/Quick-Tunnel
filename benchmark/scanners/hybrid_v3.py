"""Scanner v3 candidate: bounded parallel file inspection.

This candidate preserves the v2 per-file safety semantics (open-beneath,
regular-file checks, before/after fstat stability checks, SHA-256 hashing,
UTF-16 handling, and production secret regexes) while parallelizing independent
file inspection. It remains benchmark-only until semantic and accuracy gates
pass and a meaningful speedup is demonstrated.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .baseline import DEFAULT_MAX_FILE_BYTES, load_production_module
from .hybrid_v2 import _inspect_regular_file


def _default_workers() -> int:
    cpu = os.cpu_count() or 1
    return max(2, min(16, cpu * 2))


def scan_path(
    root: Path,
    *,
    repo_root: Path | None = None,
    maximum_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    workers: int | None = None,
) -> dict[str, Any]:
    repository = repo_root or Path(__file__).resolve().parents[2]
    production = load_production_module(repository)
    worker_count = workers or _default_workers()

    pending_directories = [root]
    candidates: list[tuple[Path, str, int, bool]] = []
    excluded_count = 0
    oversized_count = 0
    scannable_files = 0

    while pending_directories:
        directory = pending_directories.pop()
        try:
            iterator = os.scandir(directory)
        except OSError as exc:
            raise RuntimeError(f"Unable to inspect directory: {directory}") from exc

        with iterator:
            for child in iterator:
                child_path = Path(child.path)
                relative_path = child_path.relative_to(root).as_posix()

                if child.is_symlink():
                    excluded_count += 1
                    continue

                try:
                    if child.is_dir(follow_symlinks=False):
                        if (
                            child.name.casefold()
                            in production.EXCLUDED_DIRECTORY_NAMES_CASEFOLD
                            or production.matches_additional_exclude(relative_path, ())
                        ):
                            excluded_count += 1
                            continue
                        pending_directories.append(child_path)
                        continue

                    if not child.is_file(follow_symlinks=False):
                        excluded_count += 1
                        continue

                    if production.is_excluded_file_name(
                        child.name
                    ) or production.matches_additional_exclude(relative_path, ()):
                        excluded_count += 1
                        continue

                    file_size = child.stat(follow_symlinks=False).st_size
                except OSError as exc:
                    raise RuntimeError(f"Unable to inspect path: {child_path}") from exc

                if file_size > maximum_file_bytes:
                    oversized_count += 1
                    continue

                is_scannable = (
                    child_path.suffix.lower() in production.TEXT_FILE_EXTENSIONS
                    and file_size <= 2 * 1024 * 1024
                )
                scannable_files += int(is_scannable)
                candidates.append((child_path, relative_path, file_size, is_scannable))

    detections: list[str] = []
    logical_bytes = 0
    regex_evaluated_files = 0

    def inspect(candidate: tuple[Path, str, int, bool]) -> tuple[str, int, bool, bool]:
        child_path, relative_path, file_size, _is_scannable = candidate
        stable_length, _content_hash, detected, regex_evaluated = _inspect_regular_file(
            production,
            root,
            child_path,
            relative_path,
            file_size,
        )
        return relative_path, stable_length, detected, regex_evaluated

    with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="qt-scan") as executor:
        for relative_path, stable_length, detected, regex_evaluated in executor.map(
            inspect,
            candidates,
            chunksize=1,
        ):
            logical_bytes += stable_length
            regex_evaluated_files += int(regex_evaluated)
            if detected:
                detections.append(relative_path)

    return {
        "scanner": "bounded-parallel-sentinel-v3",
        "files_considered": len(candidates),
        "logical_bytes": logical_bytes,
        "estimated_physical_bytes_read": logical_bytes,
        "excluded_count": excluded_count,
        "oversized_count": oversized_count,
        "detections": sorted(detections, key=production.path_sort_key),
        "scannable_files": scannable_files,
        "regex_evaluated_files": regex_evaluated_files,
        "worker_count": worker_count,
    }
