from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
import threading
import tempfile
import unittest
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = REPO_ROOT / "safe-review-server.py"
MACOS_PATH = REPO_ROOT / "macos" / "share-codex-review.py"
WINDOWS_PATH = REPO_ROOT / "share-codex-review.ps1"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SERVER_MODULE = load_module("safe_review_server", SERVER_PATH)
MACOS_MODULE = load_module("share_codex_review_for_server_tests", MACOS_PATH)


class SafeReviewServerTests(unittest.TestCase):
    def test_cli_rejects_non_loopback_bind(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SERVER_PATH),
                    "--bind",
                    "0.0.0.0",
                    "--port",
                    "0",
                    "--directory",
                    temporary_directory,
                    "--index-name",
                    "__index__.html",
                ],
                capture_output=True,
                check=False,
                text=True,
                timeout=5,
            )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("invalid choice", completed.stderr)

    def test_windows_and_macos_scan_extension_sets_match(self) -> None:
        windows_source = WINDOWS_PATH.read_text(encoding="utf-8")
        match = re.search(
            r"\$textFileExtensions\s*=\s*@\((.*?)\n\)",
            windows_source,
            re.DOTALL,
        )
        self.assertIsNotNone(match)
        windows_extensions = set(re.findall(r"'([^']+)'", match.group(1)))
        self.assertEqual(windows_extensions, MACOS_MODULE.TEXT_FILE_EXTENSIONS)

    def test_scan_extensions_are_always_served_as_inert_text(self) -> None:
        self.assertTrue(
            MACOS_MODULE.TEXT_FILE_EXTENSIONS.issubset(
                SERVER_MODULE.TEXT_EXTENSIONS
            )
        )

    def test_mime_headers_and_path_confinement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            root = base / "share"
            root.mkdir()
            outside = base / "outside.txt"
            outside.write_text("outside", encoding="utf-8")
            (root / "__index__.html").write_text("index", encoding="utf-8")
            for name in ("source.cmd", "source.html", "source.svg", "source.js"):
                (root / name).write_text("inert", encoding="utf-8")
            (root / "unknown.bin").write_bytes(b"binary")

            handler = partial(
                SERVER_MODULE.SafeReviewRequestHandler,
                directory=str(root),
                index_name="__index__.html",
            )
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base_url = f"http://127.0.0.1:{server.server_port}"
                with urlopen(f"{base_url}/__index__.html", timeout=5) as response:
                    self.assertEqual(
                        response.headers.get_content_type(),
                        "text/html",
                    )
                    self.assertEqual(response.headers["Cache-Control"], "no-store")
                    self.assertEqual(
                        response.headers["X-Content-Type-Options"],
                        "nosniff",
                    )
                    self.assertIn("default-src 'none'", response.headers["Content-Security-Policy"])
                    self.assertEqual(
                        response.headers["Cross-Origin-Resource-Policy"],
                        "same-origin",
                    )
                    self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")

                for name in ("source.cmd", "source.html", "source.svg", "source.js"):
                    with urlopen(f"{base_url}/{name}", timeout=5) as response:
                        self.assertEqual(
                            response.headers.get_content_type(),
                            "text/plain",
                        )

                with urlopen(f"{base_url}/unknown.bin", timeout=5) as response:
                    self.assertEqual(
                        response.headers.get_content_type(),
                        "application/octet-stream",
                    )

                with self.assertRaises(HTTPError) as error:
                    urlopen(f"{base_url}/%2e%2e/outside.txt", timeout=5)
                self.assertEqual(error.exception.code, 404)
                error.exception.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
