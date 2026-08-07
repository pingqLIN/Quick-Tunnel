from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from benchmark.scanners.baseline import load_production_module
from benchmark.scanners.pipeline_v5 import (
    build_metadata_inventory,
    copy_scan_metadata_entry,
)


class PipelineV5SecurityTests(unittest.TestCase):
    def _production(self):
        return load_production_module(Path(__file__).resolve().parents[1])

    def test_same_size_mutation_after_inventory_fails_closed(self) -> None:
        production = self._production()
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source.txt"
            source.write_text("first", encoding="utf-8")
            entry = build_metadata_inventory(
                root, 1024, production=production
            ).files[0]
            source.write_text("other", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "changed since inventory"):
                copy_scan_metadata_entry(
                    production, entry, root, root / "stage" / "source.txt"
                )

    def test_inode_replacement_after_inventory_fails_closed(self) -> None:
        production = self._production()
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source.txt"
            replacement = root / "replacement.txt"
            source.write_text("first", encoding="utf-8")
            entry = build_metadata_inventory(
                root, 1024, production=production
            ).files[0]
            replacement.write_text("first", encoding="utf-8")
            os.replace(replacement, source)

            with self.assertRaisesRegex(RuntimeError, "changed since inventory"):
                copy_scan_metadata_entry(
                    production, entry, root, root / "stage" / "source.txt"
                )

    @unittest.skipUnless(
        os.open in os.supports_dir_fd
        and getattr(os, "O_NOFOLLOW", 0) != 0
        and getattr(os, "O_DIRECTORY", 0) != 0,
        "descriptor-relative no-follow traversal requires Unix support",
    )
    def test_ancestor_symlink_swap_fails_closed(self) -> None:
        production = self._production()
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            root = base / "source"
            nested = root / "nested"
            outside = base / "outside"
            nested.mkdir(parents=True)
            outside.mkdir()
            (nested / "review.txt").write_text("inside", encoding="utf-8")
            (outside / "review.txt").write_text("outside", encoding="utf-8")
            entry = build_metadata_inventory(
                root, 1024, production=production
            ).files[0]
            nested.rename(root / "nested-original")
            nested.symlink_to(outside, target_is_directory=True)

            with self.assertRaisesRegex(
                RuntimeError, "escaped or crossed a symlink"
            ):
                copy_scan_metadata_entry(
                    production,
                    entry,
                    root,
                    base / "stage" / "review.txt",
                )

    def test_copy_scans_exact_bytes_and_preserves_output(self) -> None:
        production = self._production()
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "credential.txt"
            payload = "ghp_" + "A" * 36
            source.write_text(payload, encoding="utf-8")
            entry = build_metadata_inventory(
                root, 1024, production=production
            ).files[0]
            destination = root / "stage" / "credential.txt"
            detected, digest = copy_scan_metadata_entry(
                production, entry, root, destination
            )

            self.assertTrue(detected)
            self.assertEqual(destination.read_text(encoding="utf-8"), payload)
            self.assertEqual(len(digest), 64)


if __name__ == "__main__":
    unittest.main()
