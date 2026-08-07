from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


class StagingFlushPolicyTests(unittest.TestCase):
    def test_macos_snapshot_does_not_force_per_file_fsync(self) -> None:
        source = (REPO_ROOT / "macos" / "share-codex-review.py").read_text(encoding="utf-8")
        self.assertNotIn("os.fsync(destination_file.fileno())", source)
        self.assertIn("destination_file.flush()", source)

    def test_windows_snapshot_does_not_force_durable_flush(self) -> None:
        source = (REPO_ROOT / "share-codex-review.ps1").read_text(encoding="utf-8")
        self.assertNotIn("$destinationStream.Flush($true)", source)
        self.assertIn("$destinationStream.Flush()", source)


if __name__ == "__main__":
    unittest.main()
