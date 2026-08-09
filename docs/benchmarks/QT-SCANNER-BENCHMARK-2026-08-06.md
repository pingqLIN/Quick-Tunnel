# Quick-Tunnel Scanner Benchmark — 2026-08-06

## Decision

**Keep the current production scanner.**

The benchmark infrastructure is suitable for merging, but neither tested
candidate produced a meaningful latency improvement. Production scanner files
remain unchanged.

## Scope

The cloud benchmark compared the current Python/macOS production detection
pipeline with security-equivalent candidates on a GitHub-hosted Ubuntu runner.
It measured inventory hashing plus secret detection; it did not measure staging
copy, HTTP server startup, or Cloudflare tunnel startup.

Corpus:

- 3,000 labeled safe text files
- 120 labeled synthetic secret files
- UTF-16 and malformed UTF-8 secret fixtures
- one binary fixture
- three excluded credential-shaped paths
- 3,124 eligible files
- 51,272,891 logical bytes
- no live credentials

Method:

- one warm-up
- seven timed repetitions
- alternating baseline/candidate execution order
- median and p95 latency
- labeled false-positive and false-negative measurement

## Results

### Candidate 1 — fused hashing and secret scan

This candidate read each eligible text file once and performed SHA-256 hashing
and secret detection in the same pass.

| Metric | Production baseline | Candidate 1 |
| --- | ---: | ---: |
| Median latency | 4.609265 s | 4.552349 s |
| p95 latency | 4.675282 s | 4.585833 s |
| Logical throughput | 10.61 MB/s | 10.74 MB/s |
| Estimated bytes read | 102,529,398 | 51,272,891 |
| False positives | 0 | 0 |
| False negatives | 0 | 0 |

- Relative speed: **1.013×**
- Estimated I/O reduction: **50.0%**
- Semantic parity: **passed**
- 1.15× meaningful-improvement gate: **failed**
- 3× stretch target: **failed**

### Candidate 2 — fused pass, combined regex, reduced sorting

This candidate additionally replaced seven sequential regex searches with one
combined expression and removed redundant per-directory sorting while keeping
the final output order deterministic.

| Metric | Production baseline | Candidate 2 |
| --- | ---: | ---: |
| Median latency | 5.046601 s | 5.207034 s |
| p95 latency | 5.054957 s | 5.315498 s |
| Logical throughput | 9.69 MB/s | 9.39 MB/s |
| Estimated bytes read | 102,529,398 | 51,272,891 |
| False positives | 0 | 0 |
| False negatives | 0 | 0 |

- Relative speed: **0.969×**
- Estimated I/O reduction: **50.0%**
- Semantic parity: **passed**
- 1.15× meaningful-improvement gate: **failed**
- 3× stretch target: **failed**

Absolute timings differ between hosted runners, so comparisons should use the
baseline and candidate from the same run. Both rounds reached the same decision.

## Interpretation

Reducing estimated file-content reads by half did not materially reduce total
latency. For this many-small-file workload, the dominant costs are likely:

- directory enumeration and path handling;
- secure open/no-follow checks;
- repeated `stat`/`fstat` stability validation;
- per-file SHA-256 setup and hashing;
- Python object and function-call overhead.

The second candidate shows that combining regular expressions and removing one
sorting layer are not useful optimizations for this workload. A risk-ranked or
selective deep scan was deliberately not adopted because skipping content scans
would create a new false-negative path.

## Repository action

- Merge the reproducible benchmark corpus, runner, workflow, and report format.
- Do **not** replace `macos/share-codex-review.py` or
  `share-codex-review.ps1` based on these results.
- Keep the benchmark candidate isolated under `benchmark/`.

## Next useful experiments

1. Measure the complete validate-only lifecycle, including staging copy and
   staged-hash verification. Combining scan, source hash, and staging copy may
   affect end-to-end latency more than optimizing detection alone.
2. Add a dedicated Windows PowerShell benchmark because this run directly
   exercises the Python/macOS implementation only.
3. Test bounded parallel file inspection on large repositories, with strict
   fail-closed error propagation and deterministic output.
4. Avoid persistent metadata caches as a default security shortcut; size and
   timestamp keys alone are insufficient evidence that content is unchanged.

## Evidence

- Pull request: #8
- Benchmark workflow run 1: successful
- Benchmark workflow run 2: successful after retrying a GitHub Actions service
  error that occurred before repository checkout
- Windows regression suite: passed
- macOS regression suite: passed
- Dependency review: passed
