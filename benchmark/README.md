# Quick-Tunnel Scanner Benchmark

Purpose: compare current filtering pipeline against future hybrid risk-based scanner designs.

Metrics:

- scan throughput (MB/s, files/s)
- startup latency
- total scan latency
- false positive rate
- false negative rate
- peak memory usage

Rules:

- Benchmark changes must not alter production scanner behavior.
- Replacement requires evidence that security accuracy is not degraded.

Workflow:

1. Generate reproducible corpus.
2. Run baseline scanner measurement.
3. Run candidate scanner measurement.
4. Compare reports.
