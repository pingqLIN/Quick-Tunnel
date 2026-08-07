#!/usr/bin/env python3
"""Compare production, v4, and metadata-snapshot v5 snapshot preparation."""

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

from .scanners import pipeline_v4, pipeline_v5

Pipeline = Callable[[Path], dict[str, Any]]


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def _accuracy(labels: dict[str, bool], detections: set[str]) -> dict[str, Any]:
    positives = {path for path, positive in labels.items() if positive}
    negatives = {path for path, positive in labels.items() if not positive}
    fp = sorted(detections - positives)
    fn = sorted(positives - detections)
    return {
        "false_positive": len(fp),
        "false_negative": len(fn),
        "false_positive_rate": len(fp) / len(negatives) if negatives else 0.0,
        "false_negative_rate": len(fn) / len(positives) if positives else 0.0,
        "false_positive_paths": fp,
        "false_negative_paths": fn,
    }


def _summarize(runs, durations, labels):
    representative = runs[0]
    median = statistics.median(durations)
    logical_bytes = int(representative["logical_bytes"])
    return {
        **representative,
        "duration_seconds": {
            "samples": durations,
            "mean": statistics.fmean(durations),
            "median": median,
            "p95": _percentile(durations, 0.95),
            "min": min(durations),
            "max": max(durations),
        },
        "logical_throughput_mb_s": (
            logical_bytes / (1024 * 1024) / median if median else 0.0
        ),
        "detection_consistent_across_runs": len(
            {tuple(run["detections"]) for run in runs}
        ) == 1,
        "accuracy": _accuracy(labels, set(representative["detections"])),
    }


def run_benchmark(corpus_root: Path, manifest_path: Path, repeats: int, warmups: int):
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    labels = {str(path): bool(value) for path, value in manifest["labels"].items()}
    pipelines: dict[str, Pipeline] = {
        "baseline": pipeline_v4.prepare_production,
        "v4": pipeline_v4.prepare_v4,
        "v5": pipeline_v5.prepare_v5,
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
            durations[name].append(time.perf_counter() - started)
            results[name].append(result)

    summaries = {
        name: _summarize(results[name], durations[name], labels) for name in pipelines
    }
    baseline = summaries["baseline"]
    semantic_fields = (
        "files_considered", "logical_bytes", "excluded_count", "oversized_count", "detections"
    )
    comparisons = {}
    for name in ("v4", "v5"):
        candidate = summaries[name]
        speedup = (
            baseline["duration_seconds"]["median"]
            / candidate["duration_seconds"]["median"]
        )
        semantic_parity = all(
            baseline[field] == candidate[field] for field in semantic_fields
        )
        accuracy_not_worse = (
            candidate["accuracy"]["false_negative"] <= baseline["accuracy"]["false_negative"]
            and candidate["accuracy"]["false_positive"] <= baseline["accuracy"]["false_positive"]
        )
        stable = candidate["detection_consistent_across_runs"]
        baseline_reads = baseline["estimated_physical_bytes_read"]
        candidate_reads = candidate["estimated_physical_bytes_read"]
        comparisons[name] = {
            "speedup_vs_baseline": speedup,
            "estimated_io_reduction": (
                1.0 - candidate_reads / baseline_reads if baseline_reads else 0.0
            ),
            "semantic_parity": semantic_parity,
            "accuracy_not_worse": accuracy_not_worse,
            "stable": stable,
            "meaningful_improvement_1_15x": speedup >= 1.15,
        }

    v5 = comparisons["v5"]
    performance_candidate = (
        v5["semantic_parity"]
        and v5["accuracy_not_worse"]
        and v5["stable"]
        and v5["meaningful_improvement_1_15x"]
    )
    recommendation = (
        "REVIEW_V5_SECURITY_MODEL_FOR_PRODUCTION"
        if performance_candidate
        else "KEEP_CURRENT_PRODUCTION_PIPELINE"
    )
    return {
        "schema_version": 5,
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "processor": platform.processor(),
        },
        "corpus": manifest["generator"],
        "methodology": {
            "warmups": warmups,
            "repeats": repeats,
            "scope": "inventory + staging copy/fsync + secret detection",
        },
        "pipelines": summaries,
        "comparison": comparisons,
        "v5_security_model_changed": True,
        "v5_performance_candidate": performance_candidate,
        "recommendation": recommendation,
    }


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    pipelines = report["pipelines"]
    comparisons = report["comparison"]
    lines = [
        "# Quick-Tunnel Pipeline v5 Benchmark",
        "",
        f"**{report['recommendation']}**",
        "",
        "| Metric | Production | v4 fused | v5 metadata/copy-once |",
        "| --- | ---: | ---: | ---: |",
    ]
    for label, key in (
        ("Median latency (s)", "median"),
        ("P95 latency (s)", "p95"),
    ):
        lines.append(
            f"| {label} | {pipelines['baseline']['duration_seconds'][key]:.6f} | "
            f"{pipelines['v4']['duration_seconds'][key]:.6f} | "
            f"{pipelines['v5']['duration_seconds'][key]:.6f} |"
        )
    lines += [
        f"| Estimated bytes read | {pipelines['baseline']['estimated_physical_bytes_read']} | {pipelines['v4']['estimated_physical_bytes_read']} | {pipelines['v5']['estimated_physical_bytes_read']} |",
        f"| False positives | {pipelines['baseline']['accuracy']['false_positive']} | {pipelines['v4']['accuracy']['false_positive']} | {pipelines['v5']['accuracy']['false_positive']} |",
        f"| False negatives | {pipelines['baseline']['accuracy']['false_negative']} | {pipelines['v4']['accuracy']['false_negative']} | {pipelines['v5']['accuracy']['false_negative']} |",
        "",
        "## Gates",
        f"- v4 speedup: {comparisons['v4']['speedup_vs_baseline']:.3f}x",
        f"- v5 speedup: {comparisons['v5']['speedup_vs_baseline']:.3f}x",
        f"- v5 semantic parity: {comparisons['v5']['semantic_parity']}",
        f"- v5 accuracy not worse: {comparisons['v5']['accuracy_not_worse']}",
        f"- v5 stable: {comparisons['v5']['stable']}",
        f"- v5 performance candidate: {report['v5_performance_candidate']}",
        "",
        "v5 removes the pre-copy content hash and therefore changes the integrity model. Passing performance and adversarial tests is necessary but not sufficient to claim cryptographic equivalence to production.",
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
        "v5": report["comparison"]["v5"],
        "v5_security_model_changed": True,
    }, indent=2, sort_keys=True))

    v5 = report["comparison"]["v5"]
    return 0 if (v5["semantic_parity"] and v5["accuracy_not_worse"] and v5["stable"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
