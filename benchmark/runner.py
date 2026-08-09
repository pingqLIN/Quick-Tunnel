#!/usr/bin/env python3
"""Benchmark the production scanner against a single-pass candidate."""

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

from .scanners import baseline, hybrid

Scanner = Callable[[Path], dict[str, Any]]


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def _accuracy(
    labels: dict[str, bool],
    detections: set[str],
) -> dict[str, Any]:
    expected_positive = {path for path, positive in labels.items() if positive}
    expected_negative = {path for path, positive in labels.items() if not positive}
    true_positive = len(expected_positive & detections)
    false_negative = len(expected_positive - detections)
    false_positive_paths = sorted(detections - expected_positive)
    false_positive = len(false_positive_paths)
    true_negative = len(expected_negative - detections)
    positive_total = true_positive + false_negative
    negative_total = true_negative + false_positive
    return {
        "true_positive": true_positive,
        "true_negative": true_negative,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "false_positive_rate": (
            false_positive / negative_total if negative_total else 0.0
        ),
        "false_negative_rate": (
            false_negative / positive_total if positive_total else 0.0
        ),
        "false_positive_paths": false_positive_paths,
        "false_negative_paths": sorted(expected_positive - detections),
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
    estimated_physical_bytes = int(
        representative["estimated_physical_bytes_read"]
    )
    detections = set(representative["detections"])
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
            logical_bytes / (1024 * 1024) / median_seconds
            if median_seconds
            else 0.0
        ),
        "estimated_physical_throughput_mb_s": (
            estimated_physical_bytes / (1024 * 1024) / median_seconds
            if median_seconds
            else 0.0
        ),
        "detection_consistent_across_runs": len(detection_sets) == 1,
        "accuracy": _accuracy(labels, detections),
    }


def run_benchmark(
    corpus_root: Path,
    manifest_path: Path,
    repeats: int,
    warmups: int,
) -> dict[str, Any]:
    if repeats < 1:
        raise ValueError("repeats must be at least 1")
    if warmups < 0:
        raise ValueError("warmups must be zero or greater")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    labels = {
        str(path): bool(value)
        for path, value in manifest["labels"].items()
    }

    scanners: dict[str, Scanner] = {
        "baseline": baseline.scan_path,
        "candidate": hybrid.scan_path,
    }
    for _ in range(warmups):
        for scanner in scanners.values():
            scanner(corpus_root)

    results: dict[str, list[dict[str, Any]]] = {
        name: [] for name in scanners
    }
    durations: dict[str, list[float]] = {
        name: [] for name in scanners
    }

    for repeat_index in range(repeats):
        order = (
            ("baseline", "candidate")
            if repeat_index % 2 == 0
            else ("candidate", "baseline")
        )
        for name in order:
            started = time.perf_counter()
            result = scanners[name](corpus_root)
            elapsed = time.perf_counter() - started
            results[name].append(result)
            durations[name].append(elapsed)

    baseline_summary = _summarize(
        results["baseline"],
        durations["baseline"],
        labels,
    )
    candidate_summary = _summarize(
        results["candidate"],
        durations["candidate"],
        labels,
    )

    baseline_median = baseline_summary["duration_seconds"]["median"]
    candidate_median = candidate_summary["duration_seconds"]["median"]
    speedup = (
        baseline_median / candidate_median
        if candidate_median
        else 0.0
    )
    baseline_reads = baseline_summary["estimated_physical_bytes_read"]
    candidate_reads = candidate_summary["estimated_physical_bytes_read"]
    io_reduction = (
        1.0 - candidate_reads / baseline_reads
        if baseline_reads
        else 0.0
    )

    semantic_fields = (
        "files_considered",
        "logical_bytes",
        "excluded_count",
        "oversized_count",
        "detections",
    )
    semantic_parity = all(
        baseline_summary[field] == candidate_summary[field]
        for field in semantic_fields
    )
    baseline_accuracy = baseline_summary["accuracy"]
    candidate_accuracy = candidate_summary["accuracy"]
    accuracy_not_worse = (
        candidate_accuracy["false_negative"]
        <= baseline_accuracy["false_negative"]
        and candidate_accuracy["false_positive"]
        <= baseline_accuracy["false_positive"]
    )
    stable = (
        baseline_summary["detection_consistent_across_runs"]
        and candidate_summary["detection_consistent_across_runs"]
    )
    meaningful_improvement = speedup >= 1.15
    stretch_target = speedup >= 3.0
    eligible_for_production_port = (
        semantic_parity
        and accuracy_not_worse
        and stable
        and meaningful_improvement
    )

    return {
        "schema_version": 1,
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "processor": platform.processor(),
        },
        "corpus": manifest["generator"],
        "methodology": {
            "warmups": warmups,
            "repeats": repeats,
            "order": "alternating baseline/candidate; warm-cache comparison",
            "throughput_basis": "unique eligible logical bytes",
        },
        "baseline": baseline_summary,
        "candidate": candidate_summary,
        "comparison": {
            "speedup": speedup,
            "estimated_io_reduction": io_reduction,
            "semantic_parity": semantic_parity,
            "accuracy_not_worse": accuracy_not_worse,
            "stable": stable,
            "meaningful_improvement_1_15x": meaningful_improvement,
            "stretch_target_3x": stretch_target,
            "eligible_for_production_port": eligible_for_production_port,
            "recommendation": (
                "PORT_TO_PRODUCTION"
                if eligible_for_production_port
                else "KEEP_CURRENT_PRODUCTION_SCANNER"
            ),
        },
    }


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    baseline_report = report["baseline"]
    candidate_report = report["candidate"]
    comparison = report["comparison"]
    baseline_accuracy = baseline_report["accuracy"]
    candidate_accuracy = candidate_report["accuracy"]
    lines = [
        "# Quick-Tunnel Scanner Benchmark",
        "",
        "## Decision",
        "",
        f"**{comparison['recommendation']}**",
        "",
        "The candidate is a benchmark-only single-pass implementation. "
        "Production files are not replaced by this benchmark commit.",
        "",
        "## Performance",
        "",
        "| Metric | Production baseline | Single-pass candidate |",
        "| --- | ---: | ---: |",
        (
            "| Median latency | "
            f"{baseline_report['duration_seconds']['median']:.6f} s | "
            f"{candidate_report['duration_seconds']['median']:.6f} s |"
        ),
        (
            "| P95 latency | "
            f"{baseline_report['duration_seconds']['p95']:.6f} s | "
            f"{candidate_report['duration_seconds']['p95']:.6f} s |"
        ),
        (
            "| Logical throughput | "
            f"{baseline_report['logical_throughput_mb_s']:.2f} MB/s | "
            f"{candidate_report['logical_throughput_mb_s']:.2f} MB/s |"
        ),
        (
            "| Estimated bytes read | "
            f"{baseline_report['estimated_physical_bytes_read']} | "
            f"{candidate_report['estimated_physical_bytes_read']} |"
        ),
        "",
        f"- Speedup: **{comparison['speedup']:.3f}×**",
        (
            "- Estimated scanner I/O reduction: "
            f"**{comparison['estimated_io_reduction']:.1%}**"
        ),
        f"- 1.15× meaningful-improvement gate: **{comparison['meaningful_improvement_1_15x']}**",
        f"- 3× stretch target: **{comparison['stretch_target_3x']}**",
        "",
        "## Accuracy",
        "",
        "| Metric | Production baseline | Single-pass candidate |",
        "| --- | ---: | ---: |",
        (
            "| False positives | "
            f"{baseline_accuracy['false_positive']} | "
            f"{candidate_accuracy['false_positive']} |"
        ),
        (
            "| False negatives | "
            f"{baseline_accuracy['false_negative']} | "
            f"{candidate_accuracy['false_negative']} |"
        ),
        (
            "| False-positive rate | "
            f"{baseline_accuracy['false_positive_rate']:.6%} | "
            f"{candidate_accuracy['false_positive_rate']:.6%} |"
        ),
        (
            "| False-negative rate | "
            f"{baseline_accuracy['false_negative_rate']:.6%} | "
            f"{candidate_accuracy['false_negative_rate']:.6%} |"
        ),
        "",
        f"- Semantic parity: **{comparison['semantic_parity']}**",
        f"- Accuracy not worse: **{comparison['accuracy_not_worse']}**",
        f"- Stable across repeated runs: **{comparison['stable']}**",
        "",
        "## Methodology limits",
        "",
        "- The corpus contains synthetic, non-live credential-shaped fixtures.",
        "- GitHub-hosted runner timing is suitable for relative comparison, not hardware certification.",
        "- Runs are warm-cache and alternate execution order to reduce order bias.",
        "- The benchmark measures inventory hashing plus secret detection, not staging copy or tunnel startup.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus",
        type=Path,
        default=Path("benchmark/corpus/generated"),
    )
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
        default=Path("benchmark/reports/benchmark-result.json"),
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=Path("benchmark/reports/QT-SCANNER-BENCHMARK-REPORT.md"),
    )
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be at least 1")
    if args.warmups < 0:
        parser.error("--warmups must be zero or greater")

    report = run_benchmark(
        args.corpus,
        args.manifest,
        repeats=args.repeats,
        warmups=args.warmups,
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    write_markdown(args.markdown_output, report)
    print(json.dumps(report["comparison"], indent=2, sort_keys=True))

    comparison = report["comparison"]
    if not (
        comparison["semantic_parity"]
        and comparison["accuracy_not_worse"]
        and comparison["stable"]
    ):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
