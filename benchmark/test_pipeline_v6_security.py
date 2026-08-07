from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from benchmark.scanners.baseline import load_production_module
from benchmark.scanners import pipeline_v6


class PipelineV6SecurityTests(unittest.TestCase):
    def test_same_size_mutation_after_inventory_fails_closed(self) -> None:
        production = load_production_module(Path(__file__).resolve().parents[1])
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "source"
            root.mkdir()
            source = root / "sample.txt"
            source.write_text("first", encoding="utf-8")
            entry = production.build_inventory(root, 1024).files[0]
            source.write_text("other", encoding="utf-8")
            destination = Path(temporary_directory) / "stage" / "sample.txt"
            with self.assertRaisesRegex(RuntimeError, "Source file changed during staging"):
                pipeline_v6._copy_and_scan_no_fsync(production, entry, root, destination)

    def test_secret_scan_uses_exact_copied_bytes(self) -> None:
        production = load_production_module(Path(__file__).resolve().parents[1])
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "source"
            root.mkdir()
            source = root / "credential.txt"
            secret = "ghp_" + ("Z" * 36)
            source.write_text(secret, encoding="utf-8")
            entry = production.build_inventory(root, 4096).files[0]
            destination = Path(temporary_directory) / "stage" / "credential.txt"
            detected = pipeline_v6._copy_and_scan_no_fsync(production, entry, root, destination)
            self.assertTrue(detected)
            self.assertEqual(destination.read_bytes(), source.read_bytes())


if __name__ == "__main__":
    unittest.main()
