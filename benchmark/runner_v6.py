#!/usr/bin/env python3
"""Compare production snapshot preparation, v4, and no-fsync v6."""

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

from .scanners import pipeline_v4, pipeline_v6

Pipeline = Callable[[Path], dict[str, Any]]


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
        "false_positive_rate": len(false_positive_paths) / negative_total if negative_total else 0.0,
        "false_negative_rate": len(false_negative_paths) / positive_total if positive_total else 0.0,
        "false_positive_paths": false_positive_paths,
        "false_negative_paths": false_negative_paths,
    }


def _summarize(
    runs: list[dict[str, Any]],
    durations: list[float],
    labels: dict[str, bool],
) -> dict[str, Any]:
    representative = runs[0]
    median_seconds = statistics.median(durations)
    detection_sets = {tuple(run["detections"]) for run in runs}
    logical_bytes = int(representative["logical_bytes"])
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
    pipelines: dict[str, Pipeline] = {
        "baseline": pipeline_v4.prepare_production,
        "v4": pipeline_v4.prepare_v4,
        "v6": pipeline_v6.prepare_v6,
    }

    for _ in range(warmups):
        for pipeline in pipelines.values():
            pipeline(corpus_root)

    results = {name: [] for name in pipelines}
    durations = {name: [] for name in pipelines}
    names = tuple(pipelines)
    for repeat_index in range(repeats):
        shift = repeat_index % len(names)
        order = names[shift:] + names[:shift]
        if repeat_index % 2:
            order = tuple(reversed(order))
        for name in order:
            started = time.perf_counter()
            result = pipelines[name](corpus_root)
            elapsed = time.perf_counter() - started
            results[name].append(result)
            durations[name].append(elapsed)

    summaries = {
        name: _summarize(results[name], durations[name], labels)
        for name in pipelines
    }
    baseline = summaries["baseline"]
    baseline_median = baseline["duration_seconds"]["median"]
    baseline_accuracy = baseline["accuracy"]
    semantic_fields = (
        "files_considered",
        "logical_bytes",
        "excluded_count",
        "oversized_count",
        "detections",
    )

    comparisons: dict[str, Any] = {}
    for name in ("v4", "v6"):
        candidate = summaries[name]
        candidate_median = candidate["duration_seconds"]["median"]
        accuracy = candidate["accuracy"]
        semantic_parity = all(baseline[field] == candidate[field] for field in semantic_fields)
        accuracy_not_worse = (
            accuracy["false_negative"] <= baseline_accuracy["false_negative"]
            and accuracy["false_positive"] <= baseline_accuracy["false_positive"]
        )
        stable = candidate["detection_consistent_across_runs"]
        speedup = baseline_median / candidate_median if candidate_median else 0.0
        baseline_reads = baseline["estimated_physical_bytes_read"]
        candidate_reads = candidate["estimated_physical_bytes_read"]
        io_reduction = 1.0 - candidate_reads / baseline_reads if baseline_reads else 0.0
        comparisons[name] = {
            "speedup_vs_baseline": speedup,
            "estimated_io_reduction": io_reduction,
            "semantic_parity": semantic_parity,
            "accuracy_not_worse": accuracy_not_worse,
            "stable": stable,
            "meaningful_improvement_1_15x": speedup >= 1.15,
            "eligible_for_production_port": (
                semantic_parity and accuracy_not_worse and stable and speedup >= 1.15
            ),
        }

    recommendation = (
        "PORT_V6_NO_FSYNC_TO_PRODUCTION"
        if comparisons["v6"]["eligible_for_production_port"]
        else "KEEP_CURRENT_PRODUCTION_PIPELINE"
    )
    return {
        "schema_version": 6,
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "processor": platform.processor(),
        },
        "corpus": manifest["generator"],
        "methodology": {
            "warmups": warmups,
            "repeats": repeats,
            "scope": "inventory pre-hash + staging copy + secret detection; v6 omits per-file fsync only",
            "order": "rotating/reversed warm-cache comparison",
        },
        "pipelines": summaries,
        "comparison": comparisons,
        "recommendation": recommendation,
        "v6_security_model": "source integrity unchanged; temporary-snapshot crash durability reduced",
    }


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    pipelines = report["pipelines"]
    comparisons = report["comparison"]
    lines = [
        "# Quick-Tunnel Pipeline v6 Benchmark",
        "",
        "## Decision",
        "",
        f"**{report['recommendation']}**",
        "",
        "| Metric | Production | v4 fused+fsync | v6 fused, no fsync |",
        "| --- | ---: | ---: | ---: |",
    ]
    for label, extractor in (
        ("Median latency (s)", lambda s: f"{s['duration_seconds']['median']:.6f}"),
        ("P95 latency (s)", lambda s: f"{s['duration_seconds']['p95']:.6f}"),
        ("Logical throughput (MB/s)", lambda s: f"{s['logical_throughput_mb_s']:.2f}"),
        ("False positives", lambda s: str(s['accuracy']['false_positive'])),
        ("False negatives", lambda s: str(s['accuracy']['false_negative'])),
    ):
        lines.append(
            f"| {label} | {extractor(pipelines['baseline'])} | "
            f"{extractor(pipelines['v4'])} | {extractor(pipelines['v6'])} |"
        )
    lines += [
        "",
        "## Gates",
        "",
        f"- v4 speedup: {comparisons['v4']['speedup_vs_baseline']:.3f}x",
        f"- v6 speedup: {comparisons['v6']['speedup_vs_baseline']:.3f}x",
        f"- v6 semantic_parity: {comparisons['v6']['semantic_parity']}",
        f"- v6 accuracy_not_worse: {comparisons['v6']['accuracy_not_worse']}",
        f"- v6 stable: {comparisons['v6']['stable']}",
        f"- v6 eligible_for_production_port: {comparisons['v6']['eligible_for_production_port']}",
        "",
        "v6 retains the production pre-copy SHA-256 content hash and before/after source fstat checks. It changes only temporary-snapshot crash durability by removing per-file fsync().",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=Path("benchmark/corpus/generated"))
    parser.add_argument("--manifest", type=Path, default=Path("benchmark/corpus/generated/manifest.json"))
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args()

    report = run_benchmark(args.corpus, args.manifest, args.repeats, args.warmups)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    write_markdown(args.markdown_output, report)
    print(json.dumps({
        "recommendation": report["recommendation"],
        "v4": report["comparison"]["v4"],
        "v6": report["comparison"]["v6"],
    }, indent=2, sort_keys=True))

    v6 = report["comparison"]["v6"]
    if not (v6["semantic_parity"] and v6["accuracy_not_worse"] and v6["stable"]):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
