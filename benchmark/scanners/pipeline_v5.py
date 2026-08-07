"""Benchmark-only v5: metadata inventory plus one-pass staging/hash/secret scan.

Unlike production, v5 intentionally removes the pre-copy full-file SHA-256 pass.
It records a strong metadata snapshot (device/inode/size/mtime/ctime), verifies it
when opening the source, copies through the descriptor-relative no-follow path,
scans the exact copied bytes, hashes them, fsyncs the destination, and verifies
that the opened source remained stable through the copy.

This changes the integrity model and therefore is NOT production-equivalent by
construction. It exists to quantify the performance value of the pre-hash pass.
"""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .baseline import DEFAULT_MAX_FILE_BYTES, load_production_module
from .pipeline_v4 import _scan_bytes

_SECRET_SCAN_LIMIT = 2 * 1024 * 1024
_STABLE_FIELDS = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")


@dataclass(frozen=True)
class MetadataEntry:
    source_path: Path
    relative_path: str
    length: int
    st_dev: int
    st_ino: int
    st_mtime_ns: int
    st_ctime_ns: int


@dataclass(frozen=True)
class MetadataInventory:
    files: tuple[MetadataEntry, ...]
    excluded_count: int
    oversized_count: int


def _metadata_matches(entry: MetadataEntry, value: os.stat_result) -> bool:
    return (
        value.st_dev == entry.st_dev
        and value.st_ino == entry.st_ino
        and value.st_size == entry.length
        and value.st_mtime_ns == entry.st_mtime_ns
        and value.st_ctime_ns == entry.st_ctime_ns
    )


def build_metadata_inventory(
    root: Path,
    maximum_file_bytes: int,
    *,
    production: Any,
    additional_excludes: Sequence[str] = (),
) -> MetadataInventory:
    """Enumerate eligible files without reading file contents."""
    files: list[MetadataEntry] = []
    pending_directories = [root]
    excluded_count = 0
    oversized_count = 0

    while pending_directories:
        directory = pending_directories.pop()
        try:
            children = sorted(
                os.scandir(directory),
                key=lambda item: production.path_sort_key(item.name),
            )
        except OSError as exc:
            raise RuntimeError(f"Unable to inspect directory: {directory}") from exc

        for child in children:
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
                            relative_path, additional_excludes
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
                    relative_path, additional_excludes
                ):
                    excluded_count += 1
                    continue

                info = child.stat(follow_symlinks=False)
            except OSError as exc:
                raise RuntimeError(f"Unable to inspect path: {child_path}") from exc

            if info.st_size > maximum_file_bytes:
                oversized_count += 1
                continue

            files.append(
                MetadataEntry(
                    source_path=child_path,
                    relative_path=relative_path,
                    length=info.st_size,
                    st_dev=info.st_dev,
                    st_ino=info.st_ino,
                    st_mtime_ns=info.st_mtime_ns,
                    st_ctime_ns=info.st_ctime_ns,
                )
            )

    return MetadataInventory(
        files=tuple(
            sorted(files, key=lambda item: production.path_sort_key(item.relative_path))
        ),
        excluded_count=excluded_count,
        oversized_count=oversized_count,
    )


def copy_scan_metadata_entry(
    production: Any,
    entry: MetadataEntry,
    source_root: Path,
    destination_path: Path,
) -> tuple[bool, str]:
    """Copy one metadata-snapshotted file and fail closed on observed mutation."""
    descriptor = production.open_regular_file_beneath(
        source_root, entry.relative_path, entry.source_path
    )
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or not _metadata_matches(entry, before):
            raise RuntimeError(
                f"Source file changed since inventory: {entry.relative_path}"
            )

        scannable = (
            entry.source_path.suffix.lower() in production.TEXT_FILE_EXTENSIONS
            and entry.length <= _SECRET_SCAN_LIMIT
        )
        scan_buffer = bytearray() if scannable else None
        digest = hashlib.sha256()
        destination_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with os.fdopen(descriptor, "rb", closefd=False) as source_file:
                with destination_path.open("xb") as destination_file:
                    while chunk := source_file.read(1024 * 1024):
                        destination_file.write(chunk)
                        digest.update(chunk)
                        if scan_buffer is not None:
                            scan_buffer.extend(chunk)
                    destination_file.flush()
                    os.fsync(destination_file.fileno())

            after = os.fstat(descriptor)
            if any(
                getattr(before, field) != getattr(after, field)
                for field in _STABLE_FIELDS
            ):
                raise RuntimeError(
                    f"Source file changed during staging: {entry.relative_path}"
                )
        except Exception:
            destination_path.unlink(missing_ok=True)
            raise

        detected = scan_buffer is not None and _scan_bytes(
            production, bytes(scan_buffer)
        )
        return detected, digest.hexdigest()
    finally:
        os.close(descriptor)


def prepare_v5(
    root: Path,
    *,
    repo_root: Path | None = None,
    maximum_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
) -> dict[str, Any]:
    repository = repo_root or Path(__file__).resolve().parents[2]
    production = load_production_module(repository)
    inventory = build_metadata_inventory(
        root,
        maximum_file_bytes,
        production=production,
        additional_excludes=(),
    )

    detections: list[str] = []
    with tempfile.TemporaryDirectory(prefix="qt-pipeline-v5-") as temp:
        share_root = Path(temp) / "share"
        share_root.mkdir()
        for entry in inventory.files:
            destination = share_root.joinpath(*entry.relative_path.split("/"))
            detected, _digest = copy_scan_metadata_entry(
                production, entry, root, destination
            )
            if detected:
                detections.append(entry.relative_path)

    logical_bytes = sum(entry.length for entry in inventory.files)
    return {
        "pipeline": "metadata-inventory-copy-once-v5",
        "files_considered": len(inventory.files),
        "logical_bytes": logical_bytes,
        "estimated_physical_bytes_read": logical_bytes,
        "excluded_count": inventory.excluded_count,
        "oversized_count": inventory.oversized_count,
        "detections": sorted(detections, key=production.path_sort_key),
        "integrity_model": "metadata-snapshot-plus-before-after-fstat",
        "pre_copy_content_hash": False,
    }
