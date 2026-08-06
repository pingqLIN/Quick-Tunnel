# Quick-Tunnel Scanner Benchmark

This suite compares the current macOS production scanner with a benchmark-only
single-pass candidate.

The production baseline performs inventory hashing and then rereads eligible
text files for secret detection. The candidate preserves the same exclusions,
stable-file checks, encodings, and regular expressions while computing SHA-256
and secret detection during one file read.

## Metrics

- logical scan throughput in MB/s
- median and p95 scan latency
- estimated physical bytes read
- false-positive rate
- false-negative rate
- repeated-run detection stability

## Safety gates

The benchmark does not change production behavior. A candidate is eligible for
a production port only when:

1. detected paths and inventory semantics match the production baseline;
2. false positives and false negatives do not increase;
3. results remain stable across repeated runs; and
4. median latency improves by at least 1.15x.

The original 3x improvement goal remains reported as a stretch target; it is
not assumed in advance.

## Reproduce locally

```bash
python -m benchmark.corpus.generate_corpus \
  --safe-files 3000 \
  --secret-files 120 \
  --payload-bytes 16384
python -m benchmark.runner --repeats 7 --warmups 1
```

Outputs:

- `benchmark/reports/benchmark-result.json`
- `benchmark/reports/QT-SCANNER-BENCHMARK-REPORT.md`

The corpus contains only deterministic synthetic credential-shaped fixtures.
It does not contain live secrets.
