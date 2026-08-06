#!/usr/bin/env python3
"""Compare production baseline and scanner candidates v1, v2, and v3."""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from pathlib import Path
from typing import Any, Callable

from .runner_v2 import _summarize
from .scanners import baseline, hybrid, hybrid_v2, hybrid_v3

Scanner = Callable[[Path], dict[str, Any]]


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
        "v3": hybrid_v3.scan_path,
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
            durations[name].append(time.perf_counter() - started)
            results[name].append(result)

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
    for name in ("v1", "v2", "v3"):
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
        io_reduction = 1.0 - candidate_reads / baseline_reads if baseline_reads else 0.0
        comparisons[name] = {
            "speedup_vs_baseline": speedup,
            "estimated_io_reduction": io_reduction,
            "semantic_parity": semantic_parity,
            "accuracy_not_worse": accuracy_not_worse,
            "stable": stable,
            "meaningful_improvement_1_15x": speedup >= 1.15,
            "stretch_target_3x": speedup >= 3.0,
            "eligible_for_production_port": (
                semantic_parity and accuracy_not_worse and stable and speedup >= 1.15
            ),
        }

    if comparisons["v3"]["eligible_for_production_port"]:
        recommendation = "PORT_V3_TO_PRODUCTION"
    elif comparisons["v2"]["eligible_for_production_port"]:
        recommendation = "PORT_V2_TO_PRODUCTION"
    else:
        recommendation = "KEEP_CURRENT_PRODUCTION_SCANNER"

    return {
        "schema_version": 3,
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "processor": platform.processor(),
        },
        "corpus": manifest["generator"],
        "methodology": {
            "warmups": warmups,
            "repeats": repeats,
            "order": "rotating/reversed four-way warm-cache comparison",
        },
        "scanners": summaries,
        "comparison": comparisons,
        "recommendation": recommendation,
    }


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    scanners = report["scanners"]
    comparisons = report["comparison"]
    lines = [
        "# Quick-Tunnel Scanner v3 Benchmark",
        "",
        "## Decision",
        "",
        f"**{report['recommendation']}**",
        "",
        "| Metric | Baseline | v1 fused | v2 sentinel | v3 parallel |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for label, extractor in (
        ("Median latency (s)", lambda s: f"{s['duration_seconds']['median']:.6f}"),
        ("P95 latency (s)", lambda s: f"{s['duration_seconds']['p95']:.6f}"),
        ("Logical throughput (MB/s)", lambda s: f"{s['logical_throughput_mb_s']:.2f}"),
        ("False positives", lambda s: str(s['accuracy']['false_positive'])),
        ("False negatives", lambda s: str(s['accuracy']['false_negative'])),
    ):
        lines.append(
            f"| {label} | {extractor(scanners['baseline'])} | {extractor(scanners['v1'])} | "
            f"{extractor(scanners['v2'])} | {extractor(scanners['v3'])} |"
        )

    lines += [
        "",
        "## Candidate gates",
        "",
        "| Gate | v1 | v2 | v3 |",
        "| --- | ---: | ---: | ---: |",
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
        values = [comparisons[name][key] for name in ("v1", "v2", "v3")]
        if key == "speedup_vs_baseline":
            values = [f"{value:.3f}x" for value in values]
        elif key == "estimated_io_reduction":
            values = [f"{value:.1%}" for value in values]
        lines.append(f"| {key} | {values[0]} | {values[1]} | {values[2]} |")

    lines += [
        "",
        "## v3 profiling counters",
        "",
        f"- Worker count: {scanners['v3'].get('worker_count', 0)}",
        f"- Scannable files: {scanners['v3'].get('scannable_files', 0)}",
        f"- Files requiring regex: {scanners['v3'].get('regex_evaluated_files', 0)}",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=Path("benchmark/corpus/generated"))
    parser.add_argument("--manifest", type=Path, default=Path("benchmark/corpus/generated/manifest.json"))
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--json-output", type=Path, default=Path("benchmark/reports/scanner-v3-result.json"))
    parser.add_argument("--markdown-output", type=Path, default=Path("benchmark/reports/QT-SCANNER-V3-REPORT.md"))
    args = parser.parse_args()

    report = run_benchmark(args.corpus, args.manifest, args.repeats, args.warmups)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    write_markdown(args.markdown_output, report)
    print(json.dumps({
        "recommendation": report["recommendation"],
        "v1": report["comparison"]["v1"],
        "v2": report["comparison"]["v2"],
        "v3": report["comparison"]["v3"],
    }, indent=2, sort_keys=True))

    v3 = report["comparison"]["v3"]
    if not (v3["semantic_parity"] and v3["accuracy_not_worse"] and v3["stable"]):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
