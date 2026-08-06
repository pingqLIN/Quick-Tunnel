"""End-to-end snapshot-preparation benchmark for production and v4.

v4 keeps the production inventory SHA-256 pass and staging integrity check, but
performs secret detection from the exact source bytes being copied into staging.
This removes the final reread of staged text files without weakening the
existing pre-copy content-hash / before-after fstat guarantees.
"""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
from pathlib import Path
from typing import Any

from .baseline import DEFAULT_MAX_FILE_BYTES, load_production_module

_SECRET_SCAN_LIMIT = 2 * 1024 * 1024


def _scan_bytes(production: Any, content_bytes: bytes) -> bool:
    if content_bytes.startswith((b"\xff\xfe", b"\xfe\xff")):
        content = content_bytes.decode("utf-16", errors="replace")
    else:
        content = content_bytes.decode("utf-8-sig", errors="replace")
    return any(pattern.search(content) for pattern in production.SECRET_PATTERNS)


def _copy_and_scan(
    production: Any,
    entry: Any,
    source_root: Path,
    destination_path: Path,
) -> bool:
    descriptor = production.open_regular_file_beneath(
        source_root,
        entry.relative_path,
        entry.source_path,
    )
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise RuntimeError(
                f"Source path is no longer a regular file: {entry.relative_path}"
            )
        if before.st_size != entry.length:
            raise RuntimeError(
                f"Source file changed during staging: {entry.relative_path}"
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
            ) or digest.hexdigest() != entry.content_hash:
                raise RuntimeError(
                    f"Source file changed during staging: {entry.relative_path}"
                )
        except Exception:
            destination_path.unlink(missing_ok=True)
            raise

        return scan_buffer is not None and _scan_bytes(production, bytes(scan_buffer))
    finally:
        os.close(descriptor)


def _physical_read_estimate(production: Any, inventory: Any, *, fused: bool) -> int:
    logical_bytes = sum(entry.length for entry in inventory.files)
    if fused:
        return logical_bytes * 2
    secret_scan_bytes = sum(
        entry.length
        for entry in inventory.files
        if entry.source_path.suffix.lower() in production.TEXT_FILE_EXTENSIONS
        and entry.length <= _SECRET_SCAN_LIMIT
    )
    return logical_bytes * 2 + secret_scan_bytes


def prepare_production(
    root: Path,
    *,
    repo_root: Path | None = None,
    maximum_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
) -> dict[str, Any]:
    repository = repo_root or Path(__file__).resolve().parents[2]
    production = load_production_module(repository)
    inventory = production.build_inventory(root, maximum_file_bytes, additional_excludes=())

    with tempfile.TemporaryDirectory(prefix="qt-pipeline-baseline-") as temp:
        share_root = Path(temp) / "share"
        share_root.mkdir()
        staged_entries = []
        for entry in inventory.files:
            destination_path = share_root.joinpath(*entry.relative_path.split("/"))
            production.copy_inventory_entry(entry, root, destination_path)
            staged_entries.append(
                production.InventoryEntry(
                    source_path=destination_path,
                    relative_path=entry.relative_path,
                    length=entry.length,
                    content_hash=entry.content_hash,
                )
            )
        detections = production.find_potential_secret_paths(staged_entries)

    logical_bytes = sum(entry.length for entry in inventory.files)
    return {
        "pipeline": "production-snapshot-preparation",
        "files_considered": len(inventory.files),
        "logical_bytes": logical_bytes,
        "estimated_physical_bytes_read": _physical_read_estimate(
            production, inventory, fused=False
        ),
        "excluded_count": inventory.excluded_count,
        "oversized_count": inventory.oversized_count,
        "detections": list(detections),
    }


def prepare_v4(
    root: Path,
    *,
    repo_root: Path | None = None,
    maximum_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
) -> dict[str, Any]:
    repository = repo_root or Path(__file__).resolve().parents[2]
    production = load_production_module(repository)
    inventory = production.build_inventory(root, maximum_file_bytes, additional_excludes=())

    detections: list[str] = []
    with tempfile.TemporaryDirectory(prefix="qt-pipeline-v4-") as temp:
        share_root = Path(temp) / "share"
        share_root.mkdir()
        for entry in inventory.files:
            destination_path = share_root.joinpath(*entry.relative_path.split("/"))
            if _copy_and_scan(production, entry, root, destination_path):
                detections.append(entry.relative_path)

    logical_bytes = sum(entry.length for entry in inventory.files)
    return {
        "pipeline": "staged-fused-secret-scan-v4",
        "files_considered": len(inventory.files),
        "logical_bytes": logical_bytes,
        "estimated_physical_bytes_read": _physical_read_estimate(
            production, inventory, fused=True
        ),
        "excluded_count": inventory.excluded_count,
        "oversized_count": inventory.oversized_count,
        "detections": sorted(detections, key=production.path_sort_key),
    }
