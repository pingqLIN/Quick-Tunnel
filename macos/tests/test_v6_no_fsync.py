from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "share-codex-review.py"
SPEC = importlib.util.spec_from_file_location("share_codex_review_v6_test", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load module: {MODULE_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class NoFsyncStagingTests(unittest.TestCase):
    def test_copy_keeps_integrity_without_calling_fsync(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "source"
            root.mkdir()
            source = root / "review.txt"
            payload = b"safe review payload\n"
            source.write_bytes(payload)
            entry = MODULE.build_inventory(root, maximum_file_bytes=1024).files[0]
            destination = Path(temporary_directory) / "stage" / "review.txt"

            with mock.patch.object(MODULE.os, "fsync", side_effect=AssertionError("fsync must not be called")):
                MODULE.copy_inventory_entry(entry, root, destination)

            self.assertEqual(destination.read_bytes(), payload)
            self.assertEqual(MODULE.hash_regular_file(destination, destination.name)[1], entry.content_hash)


if __name__ == "__main__":
    unittest.main()
