"""Snapshot-preparation v6: retain production pre-hash, remove per-file fsync.

v6 keeps the production inventory SHA-256 pass and all staging integrity checks.
It fuses secret detection into the staging copy like v4, but only flushes the
Python destination buffer to the OS page cache instead of forcing each temporary
snapshot file to durable storage with fsync(). The temporary snapshot is useful
only while the process is alive, so crash durability is evaluated separately
from source-content integrity and secret-detection semantics.
"""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
from pathlib import Path
from typing import Any

from .baseline import DEFAULT_MAX_FILE_BYTES, load_production_module
from .pipeline_v4 import _SECRET_SCAN_LIMIT, _scan_bytes


def _copy_and_scan_no_fsync(
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
                    # Preserve normal write visibility while avoiding durable
                    # per-file disk synchronization for an ephemeral snapshot.
                    destination_file.flush()

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


def prepare_v6(
    root: Path,
    *,
    repo_root: Path | None = None,
    maximum_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
) -> dict[str, Any]:
    repository = repo_root or Path(__file__).resolve().parents[2]
    production = load_production_module(repository)
    inventory = production.build_inventory(root, maximum_file_bytes, additional_excludes=())

    detections: list[str] = []
    with tempfile.TemporaryDirectory(prefix="qt-pipeline-v6-") as temp:
        share_root = Path(temp) / "share"
        share_root.mkdir()
        for entry in inventory.files:
            destination_path = share_root.joinpath(*entry.relative_path.split("/"))
            if _copy_and_scan_no_fsync(production, entry, root, destination_path):
                detections.append(entry.relative_path)

    logical_bytes = sum(entry.length for entry in inventory.files)
    return {
        "pipeline": "prehash-staged-fused-no-fsync-v6",
        "files_considered": len(inventory.files),
        "logical_bytes": logical_bytes,
        "estimated_physical_bytes_read": logical_bytes * 2,
        "excluded_count": inventory.excluded_count,
        "oversized_count": inventory.oversized_count,
        "detections": sorted(detections, key=production.path_sort_key),
    }
