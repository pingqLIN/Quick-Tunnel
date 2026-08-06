"""Baseline scanner adapter placeholder for Quick-Tunnel benchmark.

This module keeps benchmark orchestration independent from production code.
It will measure current scanner behavior without modifying production paths.
"""

from dataclasses import dataclass
from pathlib import Path
import time


@dataclass
class ScanResult:
    files: int
    bytes_scanned: int
    duration_seconds: float
    detections: int


def benchmark_inventory(root: Path) -> ScanResult:
    start = time.perf_counter()
    files = 0
    total_bytes = 0

    for item in root.rglob('*'):
        if item.is_file():
            files += 1
            total_bytes += item.stat().st_size

    return ScanResult(
        files=files,
        bytes_scanned=total_bytes,
        duration_seconds=time.perf_counter() - start,
        detections=0,
    )
