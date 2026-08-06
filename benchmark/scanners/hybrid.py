"""Optimized single-pass candidate with one combined secret expression.

The candidate preserves production exclusions, stable-file checks, encoding
behavior, and detection semantics. It removes a redundant per-directory sort,
reads small scannable files once, and searches one union regular expression
instead of traversing every safe file once per secret pattern.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
from pathlib import Path
from typing import Any, Pattern

from .baseline import DEFAULT_MAX_FILE_BYTES, load_production_module

_COMBINED_PATTERN_CACHE: dict[tuple[str, ...], Pattern[str]] = {}


def _combined_pattern(production: Any) -> Pattern[str]:
    key = tuple(pattern.pattern for pattern in production.SECRET_PATTERNS)
    cached = _COMBINED_PATTERN_CACHE.get(key)
    if cached is None:
        cached = re.compile(
            "|".join(f"(?:{pattern})" for pattern in key),
            re.IGNORECASE,
        )
        _COMBINED_PATTERN_CACHE[key] = cached
    return cached


def _inspect_regular_file(
    production: Any,
    combined_pattern: Pattern[str],
    root: Path,
    path: Path,
    relative_path: str,
    expected_length: int,
) -> tuple[int, str, bool]:
    try:
        descriptor = production.open_regular_file_beneath(
            root,
            relative_path,
            path,
        )
    except (OSError, RuntimeError) as exc:
        raise RuntimeError(
            f"Unable to inspect share candidate: {relative_path}"
        ) from exc

    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise RuntimeError(
                f"Source path is no longer a regular file: {relative_path}"
            )
        if before.st_size != expected_length:
            raise RuntimeError(f"Source file changed: {relative_path}")

        scannable = (
            path.suffix.lower() in production.TEXT_FILE_EXTENSIONS
            and before.st_size <= 2 * 1024 * 1024
        )
        detected = False

        with os.fdopen(descriptor, "rb", closefd=False) as source_file:
            if scannable:
                content_bytes = source_file.read()
                digest_hex = hashlib.sha256(content_bytes).hexdigest()
                if content_bytes.startswith((b"\xff\xfe", b"\xfe\xff")):
                    content = content_bytes.decode("utf-16", errors="replace")
                else:
                    content = content_bytes.decode("utf-8-sig", errors="replace")
                detected = combined_pattern.search(content) is not None
            else:
                digest = hashlib.sha256()
                while chunk := source_file.read(1024 * 1024):
                    digest.update(chunk)
                digest_hex = digest.hexdigest()

        after = os.fstat(descriptor)
        stable_fields = (
            "st_dev",
            "st_ino",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        if any(
            getattr(before, field) != getattr(after, field)
            for field in stable_fields
        ):
            raise RuntimeError(
                f"Source file changed while hashing: {relative_path}"
            )

        return before.st_size, digest_hex, detected
    finally:
        os.close(descriptor)


def scan_path(
    root: Path,
    *,
    repo_root: Path | None = None,
    maximum_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
) -> dict[str, Any]:
    repository = repo_root or Path(__file__).resolve().parents[2]
    production = load_production_module(repository)
    combined_pattern = _combined_pattern(production)

    pending_directories = [root]
    detections: list[str] = []
    logical_bytes = 0
    files_considered = 0
    excluded_count = 0
    oversized_count = 0

    while pending_directories:
        directory = pending_directories.pop()
        try:
            iterator = os.scandir(directory)
        except OSError as exc:
            raise RuntimeError(
                f"Unable to inspect directory: {directory}"
            ) from exc

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
                            or production.matches_additional_exclude(
                                relative_path,
                                (),
                            )
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
                    ) or production.matches_additional_exclude(
                        relative_path,
                        (),
                    ):
                        excluded_count += 1
                        continue

                    file_size = child.stat(follow_symlinks=False).st_size
                except OSError as exc:
                    raise RuntimeError(
                        f"Unable to inspect path: {child_path}"
                    ) from exc

                if file_size > maximum_file_bytes:
                    oversized_count += 1
                    continue

                stable_length, _content_hash, detected = _inspect_regular_file(
                    production,
                    combined_pattern,
                    root,
                    child_path,
                    relative_path,
                    file_size,
                )
                files_considered += 1
                logical_bytes += stable_length
                if detected:
                    detections.append(relative_path)

    return {
        "scanner": "fused-single-pass-combined-regex",
        "files_considered": files_considered,
        "logical_bytes": logical_bytes,
        "estimated_physical_bytes_read": logical_bytes,
        "excluded_count": excluded_count,
        "oversized_count": oversized_count,
        "detections": sorted(
            detections,
            key=production.path_sort_key,
        ),
    }
