"""Execute baseline scanner benchmark."""

from pathlib import Path
import json
import time

from quick_tunnel_baseline import scan


if __name__ == "__main__":
    root = Path("benchmark/corpus")
    start = time.perf_counter()
    result = scan(root)
    elapsed = time.perf_counter() - start

    result["duration_seconds"] = elapsed
    result["throughput_mb_s"] = (
        result["bytes_scanned"] / 1024 / 1024 / elapsed
        if elapsed else 0
    )

    output = Path("benchmark/reports/QT-SCANNER-BASELINE-001.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2),
        encoding="utf-8"
    )

    print(json.dumps(result, indent=2))
