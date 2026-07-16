"""Read-only HTTP server that renders review source files as inert content."""

from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


TEXT_EXTENSIONS = {
    ".bat",
    ".bash",
    ".c",
    ".cc",
    ".cjs",
    ".conf",
    ".config",
    ".cpp",
    ".cs",
    ".css",
    ".csv",
    ".fs",
    ".go",
    ".graphql",
    ".h",
    ".hpp",
    ".htm",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".jsonc",
    ".jsx",
    ".kt",
    ".log",
    ".md",
    ".mjs",
    ".php",
    ".ps1",
    ".psd1",
    ".psm1",
    ".py",
    ".rb",
    ".rs",
    ".scss",
    ".sh",
    ".sql",
    ".svg",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".vb",
    ".xml",
    ".yaml",
    ".yml",
    ".zsh",
}

SAFE_IMAGE_TYPES = {
    ".avif": "image/avif",
    ".bmp": "image/bmp",
    ".gif": "image/gif",
    ".ico": "image/x-icon",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


class SafeReviewRequestHandler(SimpleHTTPRequestHandler):
    """Serve a staged snapshot without executing source-controlled web files."""

    server_version = "CodexReview/1.0"
    sys_version = ""

    def __init__(self, *args: object, index_name: str, **kwargs: object) -> None:
        self.index_name = index_name
        super().__init__(*args, **kwargs)

    def guess_type(self, path: str) -> str:
        candidate = Path(path)
        if candidate.name == self.index_name:
            return "text/html; charset=utf-8"

        extension = candidate.suffix.lower()
        if extension in TEXT_EXTENSIONS:
            return "text/plain; charset=utf-8"

        return SAFE_IMAGE_TYPES.get(extension, "application/octet-stream")

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; img-src 'self'; "
            "base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
        )
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--index-name", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = args.directory.resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(root)

    handler = partial(
        SafeReviewRequestHandler,
        directory=str(root),
        index_name=args.index_name,
    )
    server = ThreadingHTTPServer((args.bind, args.port), handler)
    server.daemon_threads = True
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
