#!/usr/bin/env python3
"""Compare production baseline, v1 fused scan, and scanner v2 candidate."""

from __future__ import annotations

import argparse
import json
import math
import platform
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Callable

from .scanners import baseline, hybrid, hybrid_v2

Scanner = Callable[[Path], dict[str, Any]]


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def _accuracy(labels: dict[str, bool], detections: set[str]) -> dict[str, Any]:
    expected_positive = {path for path, positive in labels.items() if positive}
    expected_negative = {path for path, positive in labels.items() if not positive}
    false_negative_paths = sorted(expected_positive - detections)
    false_positive_paths = sorted(detections - expected_positive)
    positive_total = len(expected_positive)
    negative_total = len(expected_negative)
    return {
        "true_positive": len(expected_positive & detections),
        "true_negative": len(expected_negative - detections),
        "false_positive": len(false_positive_paths),
        "false_negative": len(false_negative_paths),
        "false_positive_rate": (
            len(false_positive_paths) / negative_total if negative_total else 0.0
        ),
        "false_negative_rate": (
            len(false_negative_paths) / positive_total if positive_total else 0.0
        ),
        "false_positive_paths": false_positive_paths,
        "false_negative_paths": false_negative_paths,
    }


def _summarize(
    runs: list[dict[str, Any]],
    durations: list[float],
    labels: dict[str, bool],
) -> dict[str, Any]:
    representative = runs[0]
    detection_sets = {tuple(run["detections"]) for run in runs}
    median_seconds = statistics.median(durations)
    logical_bytes = int(representative["logical_bytes"])
    estimated_physical_bytes = int(representative["estimated_physical_bytes_read"])
    return {
        **representative,
        "duration_seconds": {
            "samples": durations,
            "mean": statistics.fmean(durations),
            "median": median_seconds,
            "p95": _percentile(durations, 0.95),
            "min": min(durations),
            "max": max(durations),
        },
        "logical_throughput_mb_s": (
            logical_bytes / (1024 * 1024) / median_seconds if median_seconds else 0.0
        ),
        "estimated_physical_throughput_mb_s": (
            estimated_physical_bytes / (1024 * 1024) / median_seconds
            if median_seconds
            else 0.0
        ),
        "detection_consistent_across_runs": len(detection_sets) == 1,
        "accuracy": _accuracy(labels, set(representative["detections"])),
    }


def run_benchmark(
    corpus_root: Path,
    manifest_path: Path,
    repeats: int,
    warmups: int,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    labels = {str(path): bool(value) for path, value in manifest["labels"].items()}

    scanners: dict[str, Scanner] = {
        "baseline": baseline.scan_path,
        "v1": hybrid.scan_path,
        "v2": hybrid_v2.scan_path,
    }

    for _ in range(warmups):
        for scanner in scanners.values():
            scanner(corpus_root)

    results = {name: [] for name in scanners}
    durations = {name: [] for name in scanners}
    names = tuple(scanners)

    for repeat_index in range(repeats):
        shift = repeat_index % len(names)
        order = names[shift:] + names[:shift]
        if repeat_index % 2:
            order = tuple(reversed(order))
        for name in order:
            started = time.perf_counter()
            result = scanners[name](corpus_root)
            elapsed = time.perf_counter() - started
            results[name].append(result)
            durations[name].append(elapsed)

    summaries = {
        name: _summarize(results[name], durations[name], labels)
        for name in scanners
    }

    baseline_summary = summaries["baseline"]
    baseline_median = baseline_summary["duration_seconds"]["median"]
    baseline_accuracy = baseline_summary["accuracy"]
    semantic_fields = (
        "files_considered",
        "logical_bytes",
        "excluded_count",
        "oversized_count",
        "detections",
    )

    comparisons: dict[str, Any] = {}
    for name in ("v1", "v2"):
        candidate = summaries[name]
        candidate_median = candidate["duration_seconds"]["median"]
        accuracy = candidate["accuracy"]
        semantic_parity = all(
            baseline_summary[field] == candidate[field]
            for field in semantic_fields
        )
        accuracy_not_worse = (
            accuracy["false_negative"] <= baseline_accuracy["false_negative"]
            and accuracy["false_positive"] <= baseline_accuracy["false_positive"]
        )
        stable = candidate["detection_consistent_across_runs"]
        speedup = baseline_median / candidate_median if candidate_median else 0.0
        baseline_reads = baseline_summary["estimated_physical_bytes_read"]
        candidate_reads = candidate["estimated_physical_bytes_read"]
        io_reduction = (
            1.0 - candidate_reads / baseline_reads if baseline_reads else 0.0
        )
        comparisons[name] = {
            "speedup_vs_baseline": speedup,
            "estimated_io_reduction": io_reduction,
            "semantic_parity": semantic_parity,
            "accuracy_not_worse": accuracy_not_worse,
            "stable": stable,
            "meaningful_improvement_1_15x": speedup >= 1.15,
            "stretch_target_3x": speedup >= 3.0,
            "eligible_for_production_port": (
                semantic_parity
                and accuracy_not_worse
                and stable
                and speedup >= 1.15
            ),
        }

    recommendation = (
        "PORT_V2_TO_PRODUCTION"
        if comparisons["v2"]["eligible_for_production_port"]
        else "KEEP_CURRENT_PRODUCTION_SCANNER"
    )

    return {
        "schema_version": 2,
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "processor": platform.processor(),
        },
        "corpus": manifest["generator"],
        "methodology": {
            "warmups": warmups,
            "repeats": repeats,
            "order": "rotating/reversed three-way warm-cache comparison",
        },
        "scanners": summaries,
        "comparison": comparisons,
        "recommendation": recommendation,
    }


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    scanners = report["scanners"]
    comparisons = report["comparison"]
    lines = [
        "# Quick-Tunnel Scanner v2 Benchmark",
        "",
        "## Decision",
        "",
        f"**{report['recommendation']}**",
        "",
        "| Metric | Baseline | v1 fused | v2 sentinel-gated |",
        "| --- | ---: | ---: | ---: |",
    ]
    for label, extractor in (
        ("Median latency (s)", lambda s: f"{s['duration_seconds']['median']:.6f}"),
        ("P95 latency (s)", lambda s: f"{s['duration_seconds']['p95']:.6f}"),
        ("Logical throughput (MB/s)", lambda s: f"{s['logical_throughput_mb_s']:.2f}"),
        ("Estimated bytes read", lambda s: str(s['estimated_physical_bytes_read'])),
        ("False positives", lambda s: str(s['accuracy']['false_positive'])),
        ("False negatives", lambda s: str(s['accuracy']['false_negative'])),
    ):
        lines.append(
            f"| {label} | {extractor(scanners['baseline'])} | "
            f"{extractor(scanners['v1'])} | {extractor(scanners['v2'])} |"
        )

    lines += [
        "",
        "## Candidate gates",
        "",
        "| Gate | v1 | v2 |",
        "| --- | ---: | ---: |",
    ]
    for key in (
        "speedup_vs_baseline",
        "estimated_io_reduction",
        "semantic_parity",
        "accuracy_not_worse",
        "stable",
        "meaningful_improvement_1_15x",
        "stretch_target_3x",
        "eligible_for_production_port",
    ):
        v1 = comparisons["v1"][key]
        v2 = comparisons["v2"][key]
        if key == "speedup_vs_baseline":
            v1, v2 = f"{v1:.3f}x", f"{v2:.3f}x"
        elif key == "estimated_io_reduction":
            v1, v2 = f"{v1:.1%}", f"{v2:.1%}"
        lines.append(f"| {key} | {v1} | {v2} |")

    lines += [
        "",
        "## v2 profiling counters",
        "",
        f"- Scannable files: {scanners['v2'].get('scannable_files', 0)}",
        f"- Files requiring regex: {scanners['v2'].get('regex_evaluated_files', 0)}",
    ]

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=Path("benchmark/corpus/generated"))
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("benchmark/corpus/generated/manifest.json"),
    )
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path("benchmark/reports/scanner-v2-result.json"),
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=Path("benchmark/reports/QT-SCANNER-V2-REPORT.md"),
    )
    args = parser.parse_args()

    report = run_benchmark(args.corpus, args.manifest, args.repeats, args.warmups)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    write_markdown(args.markdown_output, report)
    print(json.dumps({
        "recommendation": report["recommendation"],
        "v1": report["comparison"]["v1"],
        "v2": report["comparison"]["v2"],
    }, indent=2, sort_keys=True))

    v2 = report["comparison"]["v2"]
    if not (v2["semantic_parity"] and v2["accuracy_not_worse"] and v2["stable"]):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
