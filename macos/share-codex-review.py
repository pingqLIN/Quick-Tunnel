#!/usr/bin/env python3
"""Share a filtered folder snapshot through a temporary Cloudflare Quick Tunnel."""

from __future__ import annotations

import argparse
import fnmatch
import html
import os
import re
import select
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import BinaryIO, Iterable, Sequence
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


EXCLUDED_DIRECTORY_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".del",
    "node_modules",
    "bower_components",
    ".venv",
    "venv",
    "__pycache__",
    ".next",
    ".nuxt",
    ".cache",
    ".terraform",
    ".wrangler",
    ".cloudflared",
    ".ssh",
    ".gnupg",
    ".aws",
    ".azure",
    ".gcloud",
}
EXCLUDED_DIRECTORY_NAMES_CASEFOLD = {
    name.casefold() for name in EXCLUDED_DIRECTORY_NAMES
}

EXCLUDED_FILE_PATTERNS = (
    ".env",
    ".env.*",
    ".npmrc",
    ".netrc",
    ".pypirc",
    "*.pem",
    "*.key",
    "*.pfx",
    "*.p12",
    "*.ppk",
    "*.kdbx",
    "*.jks",
    "*.keystore",
    "id_rsa*",
    "id_ed25519*",
    "id_ecdsa*",
    "id_dsa*",
    "credentials*.json",
    "service-account*.json",
    "secrets.*",
    "*.tfstate",
    "*.tfstate.*",
)

TEXT_FILE_EXTENSIONS = {
    ".ps1",
    ".psm1",
    ".psd1",
    ".py",
    ".js",
    ".mjs",
    ".cjs",
    ".jsx",
    ".ts",
    ".tsx",
    ".json",
    ".jsonc",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".config",
    ".conf",
    ".md",
    ".txt",
    ".html",
    ".htm",
    ".css",
    ".scss",
    ".xml",
    ".cs",
    ".fs",
    ".vb",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".rb",
    ".php",
    ".sh",
    ".bash",
    ".zsh",
    ".bat",
    ".cmd",
    ".sql",
    ".graphql",
}

SECRET_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----",
        r"\bAKIA[0-9A-Z]{16}\b",
        r"\bgh[pousr]_[A-Za-z0-9]{36,255}\b",
        r"\bgithub_pat_[A-Za-z0-9_]{20,255}\b",
        r"\bsk-(?:proj-|svcacct-|ant-api\d{2}-)?[A-Za-z0-9_-]{20,255}\b",
        r"\bxox[baprs]-[A-Za-z0-9-]{10,255}\b",
        r"\bAIza[0-9A-Za-z_-]{35}\b",
    )
)

QUICK_TUNNEL_URL_PATTERN = re.compile(
    r"https://[a-z0-9-]+\.trycloudflare\.com",
    re.IGNORECASE,
)
ERROR_LINE_PATTERN = re.compile(
    r"\b(ERR|FTL|error|failed|failure|timeout|unable|denied|refused)\b",
    re.IGNORECASE,
)
SENSITIVE_VALUE_PATTERN = re.compile(
    r"(authorization|token|secret|password)(\s*[:=]\s*)(?:Bearer\s+)?\S+",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class InventoryEntry:
    source_path: Path
    relative_path: str
    length: int


@dataclass(frozen=True)
class ShareInventory:
    files: tuple[InventoryEntry, ...]
    excluded_count: int
    oversized_count: int


@dataclass(frozen=True)
class SharedFile:
    original_relative_path: str
    shared_relative_path: str
    length: int


@dataclass
class ManagedProcess:
    process: subprocess.Popen[bytes]
    stdout_handle: BinaryIO
    stderr_handle: BinaryIO


def path_sort_key(value: str) -> tuple[str, str, str]:
    """Return a stable filename order across case and Unicode variants."""

    normalized_value = unicodedata.normalize("NFC", value)
    return (normalized_value.casefold(), normalized_value, value)


def matches_pattern(value: str, pattern: str) -> bool:
    """Match using case-insensitive shell wildcard semantics."""

    return fnmatch.fnmatchcase(value.casefold(), pattern.casefold())


def matches_additional_exclude(relative_path: str, patterns: Sequence[str]) -> bool:
    return any(matches_pattern(relative_path, pattern) for pattern in patterns)


def is_excluded_file_name(name: str) -> bool:
    return any(matches_pattern(name, pattern) for pattern in EXCLUDED_FILE_PATTERNS)


def build_inventory(
    root_path: Path,
    maximum_file_bytes: int,
    additional_excludes: Sequence[str] = (),
) -> ShareInventory:
    """Enumerate shareable files without following symlinks."""

    files: list[InventoryEntry] = []
    pending_directories = [root_path]
    excluded_count = 0
    oversized_count = 0

    while pending_directories:
        directory = pending_directories.pop()
        try:
            children = sorted(
                os.scandir(directory),
                key=lambda item: path_sort_key(item.name),
            )
        except OSError as exc:
            raise RuntimeError(f"Unable to inspect directory: {directory}") from exc

        for child in children:
            child_path = Path(child.path)
            relative_path = child_path.relative_to(root_path).as_posix()

            if child.is_symlink():
                excluded_count += 1
                continue

            try:
                if child.is_dir(follow_symlinks=False):
                    if (
                        child.name.casefold() in EXCLUDED_DIRECTORY_NAMES_CASEFOLD
                        or matches_additional_exclude(relative_path, additional_excludes)
                    ):
                        excluded_count += 1
                        continue

                    pending_directories.append(child_path)
                    continue

                if not child.is_file(follow_symlinks=False):
                    excluded_count += 1
                    continue

                if is_excluded_file_name(child.name) or matches_additional_exclude(
                    relative_path,
                    additional_excludes,
                ):
                    excluded_count += 1
                    continue

                file_size = child.stat(follow_symlinks=False).st_size
            except OSError as exc:
                raise RuntimeError(f"Unable to inspect path: {child_path}") from exc

            if file_size > maximum_file_bytes:
                oversized_count += 1
                continue

            files.append(
                InventoryEntry(
                    source_path=child_path,
                    relative_path=relative_path,
                    length=file_size,
                )
            )

    return ShareInventory(
        files=tuple(
            sorted(files, key=lambda item: path_sort_key(item.relative_path))
        ),
        excluded_count=excluded_count,
        oversized_count=oversized_count,
    )


def contains_potential_secret(entry: InventoryEntry) -> bool:
    if entry.source_path.suffix.lower() not in TEXT_FILE_EXTENSIONS:
        return False
    if entry.length > 2 * 1024 * 1024:
        return False

    try:
        content = entry.source_path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        raise RuntimeError(f"Unable to scan file: {entry.relative_path}") from exc

    return any(pattern.search(content) for pattern in SECRET_PATTERNS)


def find_potential_secret_paths(
    entries: Iterable[InventoryEntry],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            (
                entry.relative_path
                for entry in entries
                if contains_potential_secret(entry)
            ),
            key=path_sort_key,
        )
    )


def choose_index_file_name(relative_paths: Iterable[str]) -> str:
    existing = {relative_path.casefold() for relative_path in relative_paths}
    suffix = 0
    while True:
        candidate = (
            "__codex_review__.html"
            if suffix == 0
            else f"__codex_review_{suffix}.html"
        )
        if candidate.casefold() not in existing:
            return candidate
        suffix += 1


def format_file_size(length: int) -> str:
    if length < 1024:
        return f"{length} B"
    if length < 1024 * 1024:
        return f"{length / 1024:.1f} KB"
    return f"{length / (1024 * 1024):.1f} MB"


def url_path(relative_path: str) -> str:
    return "/".join(quote(segment, safe="") for segment in relative_path.split("/"))


def write_review_index(
    destination_path: Path,
    shared_files: Sequence[SharedFile],
    source_folder_name: str,
    excluded_count: int,
    oversized_count: int,
) -> None:
    rows = []
    for shared_file in sorted(
        shared_files,
        key=lambda item: path_sort_key(item.original_relative_path),
    ):
        safe_path = html.escape(shared_file.original_relative_path, quote=True)
        safe_href = html.escape(url_path(shared_file.shared_relative_path), quote=True)
        rows.append(
            f'    <li><a href="{safe_href}">{safe_path}</a>'
            f'<span class="size">{format_file_size(shared_file.length)}</span></li>'
        )

    safe_folder_name = html.escape(source_folder_name, quote=True)
    document = "\n".join(
        (
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '  <meta charset="utf-8">',
            '  <meta name="viewport" content="width=device-width, initial-scale=1">',
            '  <meta name="referrer" content="no-referrer">',
            '  <meta name="codex-review-index" content="true">',
            "  <meta http-equiv=\"Content-Security-Policy\" "
            "content=\"default-src 'none'; style-src 'unsafe-inline'\">",
            "  <title>Codex review files</title>",
            "  <style>body{font:16px/1.5 system-ui,sans-serif;max-width:1100px;"
            "margin:2rem auto;padding:0 1rem;color:#1f2937}h1{margin-bottom:.25rem}"
            ".meta{color:#6b7280}ul{padding-left:1.25rem}li{margin:.35rem 0}"
            "a{color:#075985;text-decoration:none}a:hover{text-decoration:underline}"
            ".size{color:#6b7280;font-size:.85em;margin-left:.5rem}"
            "code{background:#f3f4f6;padding:.1rem .3rem;border-radius:.25rem}</style>",
            "</head>",
            "<body>",
            "  <h1>Codex review files</h1>",
            f'  <p class="meta">Filtered read-only snapshot of '
            f"<code>{safe_folder_name}</code>. {len(shared_files)} files shared; "
            f"{excluded_count} paths excluded; {oversized_count} oversized files "
            "skipped.</p>",
            "  <ul>",
            *rows,
            "  </ul>",
            "</body>",
            "</html>",
            "",
        )
    )
    with destination_path.open("w", encoding="utf-8", newline="\n") as output_file:
        output_file.write(document)


def copy_inventory_entry(
    entry: InventoryEntry,
    source_root: Path,
    destination_path: Path,
) -> None:
    """Copy a checked regular file into staging without following a final symlink."""

    source_path = entry.source_path
    if source_path.is_symlink():
        raise RuntimeError(
            f"Source path became a symlink during staging: {entry.relative_path}"
        )

    try:
        resolved_source_root = source_root.resolve(strict=True)
        resolved_source = source_path.resolve(strict=True)
        resolved_source.relative_to(resolved_source_root)
    except (OSError, ValueError) as exc:
        raise RuntimeError(
            f"Source path escaped the selected folder: {entry.relative_path}"
        ) from exc

    flags = os.O_RDONLY
    flags |= getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    file_descriptor = os.open(source_path, flags)
    try:
        source_stat = os.fstat(file_descriptor)
        if not stat.S_ISREG(source_stat.st_mode):
            raise RuntimeError(
                f"Source path is no longer a regular file: {entry.relative_path}"
            )
        if source_stat.st_size != entry.length:
            raise RuntimeError(
                f"Source file changed during staging: {entry.relative_path}"
            )

        destination_path.parent.mkdir(parents=True, exist_ok=True)
        with os.fdopen(file_descriptor, "rb", closefd=False) as source_file:
            with destination_path.open("xb") as destination_file:
                shutil.copyfileobj(source_file, destination_file)
    finally:
        os.close(file_descriptor)


def get_available_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def locate_safe_server() -> Path:
    script_directory = Path(__file__).resolve().parent
    candidates = (
        script_directory / "safe-review-server.py",
        script_directory.parent / "safe-review-server.py",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "safe-review-server.py was not found beside the macOS script or repo root."
    )


def start_logged_process(
    command: Sequence[str],
    stdout_path: Path,
    stderr_path: Path,
) -> ManagedProcess:
    stdout_handle = stdout_path.open("wb")
    stderr_handle = stderr_path.open("wb")
    kwargs: dict[str, object] = {}
    if os.name != "nt":
        kwargs["start_new_session"] = True

    try:
        process = subprocess.Popen(
            list(command),
            stdin=subprocess.DEVNULL,
            stdout=stdout_handle,
            stderr=stderr_handle,
            **kwargs,
        )
    except Exception:
        stdout_handle.close()
        stderr_handle.close()
        raise

    return ManagedProcess(
        process=process,
        stdout_handle=stdout_handle,
        stderr_handle=stderr_handle,
    )


def stop_process(managed_process: ManagedProcess | None) -> None:
    if managed_process is None:
        return

    process = managed_process.process
    if process.poll() is None:
        if os.name == "nt":
            process.terminate()
        else:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                process.kill()
            else:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            process.wait(timeout=5)

    if not managed_process.stdout_handle.closed:
        managed_process.stdout_handle.close()
    if not managed_process.stderr_handle.closed:
        managed_process.stderr_handle.close()


def wait_for_local_server(
    process: subprocess.Popen[bytes],
    url: str,
) -> None:
    for _ in range(25):
        exit_code = process.poll()
        if exit_code is not None:
            raise RuntimeError(f"Local HTTP server exited with code {exit_code}.")

        try:
            request = Request(url, method="HEAD")
            with urlopen(request, timeout=2) as response:
                if response.status == 200:
                    return
        except (OSError, URLError):
            time.sleep(0.25)

    raise TimeoutError(f"Local HTTP server did not become ready: {url}")


def read_log_text(log_paths: Sequence[Path]) -> str:
    parts = []
    for log_path in log_paths:
        if log_path.is_file():
            parts.append(log_path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(parts)


def wait_for_quick_tunnel_url(
    process: subprocess.Popen[bytes],
    log_paths: Sequence[Path],
    timeout_seconds: int = 90,
) -> str:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        match = QUICK_TUNNEL_URL_PATTERN.search(read_log_text(log_paths))
        if match:
            return match.group(0)

        exit_code = process.poll()
        if exit_code is not None:
            raise RuntimeError(
                "Cloudflare Tunnel exited with code "
                f"{exit_code} before publishing a URL."
            )
        time.sleep(0.5)

    raise TimeoutError("Timed out waiting for the Cloudflare Quick Tunnel URL.")


def is_retryable_quick_tunnel_failure(log_content: str) -> bool:
    is_server_failure = bool(
        re.search(r'status_code="5\d{2}', log_content, re.IGNORECASE)
        or re.search(r"\b500 Internal Server Error\b", log_content, re.IGNORECASE)
        or re.search(r"error code:\s*1101\b", log_content, re.IGNORECASE)
    )
    is_malformed_response = bool(
        re.search(
            r"Error unmarshaling QuickTunnel response",
            log_content,
            re.IGNORECASE,
        )
        or re.search(
            r"failed to unmarshal quick Tunnel",
            log_content,
            re.IGNORECASE,
        )
    )
    return is_server_failure and is_malformed_response


def verify_public_review_url(url: str) -> str | None:
    for _ in range(8):
        try:
            with urlopen(url, timeout=10) as response:
                content_type = response.headers.get("Content-Type", "")
                content = response.read().decode("utf-8", errors="replace")
                if (
                    response.status == 200
                    and content_type.lower().startswith("text/html")
                    and 'name="codex-review-index"' in content
                ):
                    return content_type
        except (OSError, URLError):
            pass
        time.sleep(2)
    return None


def get_tunnel_error_summary(log_paths: Sequence[Path]) -> tuple[str, ...]:
    diagnostics: list[str] = []
    for log_path in log_paths:
        if not log_path.is_file():
            continue
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in lines[-30:]:
            if ERROR_LINE_PATTERN.search(line):
                diagnostics.append(
                    SENSITIVE_VALUE_PATTERN.sub(r"\1\2[REDACTED]", line)
                )
    return tuple(diagnostics[-10:])


def wait_for_stop(duration_minutes: int) -> bool:
    """Wait for Enter or timeout. Return True when the timeout wins."""

    timeout_seconds = duration_minutes * 60
    if not sys.stdin.isatty():
        time.sleep(timeout_seconds)
        return True

    ready, _, _ = select.select([sys.stdin], [], [], timeout_seconds)
    if ready:
        sys.stdin.readline()
        return False
    return True


def bounded_integer(minimum: int, maximum: int):
    def parse(value: str) -> int:
        parsed = int(value)
        if not minimum <= parsed <= maximum:
            raise argparse.ArgumentTypeError(
                f"must be between {minimum} and {maximum}"
            )
        return parsed

    return parse


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--port", type=bounded_integer(0, 65535), default=0)
    parser.add_argument(
        "--duration-minutes",
        type=bounded_integer(1, 1440),
        default=30,
    )
    parser.add_argument(
        "--max-file-size-mb",
        type=bounded_integer(1, 10240),
        default=25,
    )
    parser.add_argument(
        "--quick-tunnel-attempts",
        type=bounded_integer(1, 5),
        default=3,
    )
    parser.add_argument(
        "--quick-tunnel-retry-base-seconds",
        type=bounded_integer(1, 60),
        default=5,
    )
    parser.add_argument(
        "--additional-exclude",
        action="append",
        default=[],
        metavar="PATTERN",
        help="Case-insensitive wildcard path to exclude; repeat as needed.",
    )
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--no-qr-code", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--wait-for-acknowledgement", action="store_true")
    return parser


def run_review(args: argparse.Namespace) -> int:
    server_process: ManagedProcess | None = None
    tunnel_process: ManagedProcess | None = None
    tunnel_log_paths: tuple[Path, ...] = ()
    temporary_directory: tempfile.TemporaryDirectory[str] | None = None
    sharing_started = False
    stopped_by_timeout = False
    exit_code = 0

    try:
        resolved_path = args.folder.expanduser().resolve(strict=True)
        if not resolved_path.is_dir():
            raise NotADirectoryError(f"Folder not found: {args.folder}")

        safe_server_path = locate_safe_server()
        print(f"Preparing filtered snapshot: {resolved_path}")
        inventory = build_inventory(
            resolved_path,
            maximum_file_bytes=args.max_file_size_mb * 1024 * 1024,
            additional_excludes=args.additional_exclude,
        )
        if not inventory.files:
            raise RuntimeError("No shareable files remain after exclusions.")

        temporary_directory = tempfile.TemporaryDirectory(
            prefix="share-codex-review-"
        )
        temporary_root = Path(temporary_directory.name)
        share_root = temporary_root / "share"
        share_root.mkdir()

        index_file_name = choose_index_file_name(
            entry.relative_path for entry in inventory.files
        )
        staged_entries: list[InventoryEntry] = []
        shared_files: list[SharedFile] = []
        for entry in inventory.files:
            destination_path = share_root.joinpath(*entry.relative_path.split("/"))
            copy_inventory_entry(entry, resolved_path, destination_path)
            staged_entries.append(
                InventoryEntry(
                    source_path=destination_path,
                    relative_path=entry.relative_path,
                    length=entry.length,
                )
            )
            shared_files.append(
                SharedFile(
                    original_relative_path=entry.relative_path,
                    shared_relative_path=entry.relative_path,
                    length=entry.length,
                )
            )

        potential_secret_paths = find_potential_secret_paths(staged_entries)
        if potential_secret_paths:
            path_list = "\n".join(f"  - {path}" for path in potential_secret_paths)
            raise RuntimeError(
                "Potential secret material was detected. Nothing was shared. "
                "Exclude or sanitize these files and retry:\n"
                f"{path_list}"
            )

        write_review_index(
            share_root / index_file_name,
            shared_files,
            source_folder_name=resolved_path.name or resolved_path.anchor,
            excluded_count=inventory.excluded_count,
            oversized_count=inventory.oversized_count,
        )
        print(
            f"Snapshot ready: {len(shared_files)} files; "
            f"{inventory.excluded_count} excluded; "
            f"{inventory.oversized_count} oversized."
        )

        port = args.port or get_available_loopback_port()
        local_base_url = f"http://127.0.0.1:{port}"
        local_review_url = f"{local_base_url}/{index_file_name}"
        server_process = start_logged_process(
            (
                sys.executable,
                str(safe_server_path),
                "--port",
                str(port),
                "--bind",
                "127.0.0.1",
                "--directory",
                str(share_root),
                "--index-name",
                index_file_name,
            ),
            temporary_root / "python.stdout.log",
            temporary_root / "python.stderr.log",
        )
        wait_for_local_server(server_process.process, local_review_url)
        print(
            "Local read-only server verified: "
            f"{local_review_url} (PID {server_process.process.pid})"
        )

        if args.validate_only:
            print("Validation complete. No public tunnel was opened.")
            return 0

        print()
        print("PUBLIC SHARING WARNING")
        print(
            "Anyone with the generated URL can access the filtered snapshot "
            "until this process stops."
        )
        print("The URL is not protected by a password or Cloudflare Access.")
        if not args.yes:
            approval = input(
                "Type SHARE to open the public tunnel (anything else cancels): "
            )
            if approval != "SHARE":
                print("Sharing cancelled. No public tunnel was opened.")
                return 0

        cloudflared_path = shutil.which("cloudflared")
        if cloudflared_path is None:
            raise FileNotFoundError(
                "cloudflared was not found. Install it and add it to PATH."
            )

        isolated_config_path = temporary_root / "cloudflared-empty.yml"
        with isolated_config_path.open(
            "w", encoding="utf-8", newline="\n"
        ) as config_file:
            config_file.write("{}")
        tunnel_command = (
            cloudflared_path,
            "tunnel",
            "--config",
            str(isolated_config_path),
            "--url",
            local_base_url,
            "--no-autoupdate",
            "--management-diagnostics=false",
            "--loglevel",
            "info",
        )

        public_base_url: str | None = None
        for tunnel_attempt in range(1, args.quick_tunnel_attempts + 1):
            stdout_path = (
                temporary_root
                / f"cloudflared-attempt-{tunnel_attempt}.stdout.log"
            )
            stderr_path = (
                temporary_root
                / f"cloudflared-attempt-{tunnel_attempt}.stderr.log"
            )
            tunnel_log_paths = (stdout_path, stderr_path)
            tunnel_process = start_logged_process(
                tunnel_command,
                stdout_path,
                stderr_path,
            )
            try:
                public_base_url = wait_for_quick_tunnel_url(
                    tunnel_process.process,
                    tunnel_log_paths,
                )
                break
            except (RuntimeError, TimeoutError) as startup_error:
                stop_process(tunnel_process)
                retryable = is_retryable_quick_tunnel_failure(
                    read_log_text(tunnel_log_paths)
                )
                if (
                    not retryable
                    or tunnel_attempt == args.quick_tunnel_attempts
                ):
                    raise startup_error

                retry_delay_seconds = min(
                    args.quick_tunnel_retry_base_seconds
                    * (2 ** (tunnel_attempt - 1)),
                    60,
                )
                print(
                    "WARNING: Cloudflare Quick Tunnel returned a transient "
                    "500/1101 response. Retrying attempt "
                    f"{tunnel_attempt + 1} of {args.quick_tunnel_attempts} in "
                    f"{retry_delay_seconds} second(s)."
                )
                time.sleep(retry_delay_seconds)

        if public_base_url is None:
            raise RuntimeError("Cloudflare Quick Tunnel did not publish a URL.")

        public_review_url = f"{public_base_url}/{index_file_name}"
        sharing_started = True
        public_content_type = verify_public_review_url(public_review_url)
        print()
        print("Share URL:")
        print(public_review_url)
        if public_content_type is not None:
            print(f"Public verification: HTTP 200, {public_content_type}")
        else:
            print(
                "WARNING: The tunnel URL was created, but verification from "
                "this Mac did not succeed. VM or NAT self-access policies can "
                "cause this; verify from the intended external client."
            )
        print(
            f"Server PID: {server_process.process.pid} | "
            f"Tunnel PID: {tunnel_process.process.pid}"
        )

        if not args.no_qr_code:
            qrencode_path = shutil.which("qrencode")
            if qrencode_path is not None:
                print()
                subprocess.run(
                    (qrencode_path, "-t", "ANSIUTF8", public_review_url),
                    check=False,
                )
            else:
                print("QR code: qrencode is not installed; use the URL above.")

        stop_time = datetime.now().astimezone() + timedelta(
            minutes=args.duration_minutes
        )
        print()
        print(f"Quick Tunnel lifetime: {args.duration_minutes} minute(s).")
        print(
            "Press ENTER to stop early. Automatic stop: "
            f"{stop_time.isoformat(sep=' ', timespec='seconds')}"
        )
        stopped_by_timeout = wait_for_stop(args.duration_minutes)
        if stopped_by_timeout:
            print(
                "Quick Tunnel lifetime expired. Stopping public sharing now."
            )
    except KeyboardInterrupt:
        print("\nStopping public sharing.")
    except Exception as exc:
        exit_code = 1
        print(f"ERROR: {exc}", file=sys.stderr)
        diagnostics = get_tunnel_error_summary(tunnel_log_paths)
        if diagnostics:
            print("cloudflared diagnostic summary:", file=sys.stderr)
            for diagnostic in diagnostics:
                print(f"  {diagnostic}", file=sys.stderr)
    finally:
        stop_process(tunnel_process)
        stop_process(server_process)
        if temporary_directory is not None:
            temporary_directory.cleanup()

        if sharing_started:
            stopped_at = datetime.now().astimezone().isoformat(
                sep=" ",
                timespec="seconds",
            )
            print(
                f"Sharing stopped at {stopped_at}. Temporary files were removed."
            )

        if args.wait_for_acknowledgement and (
            stopped_by_timeout or exit_code != 0
        ):
            prompt = (
                "Startup failed. Review the error above, then press ENTER to close "
                "this window"
                if exit_code != 0
                else "Quick Tunnel has expired and is closed. Press ENTER to close "
                "this window"
            )
            try:
                input(prompt)
            except EOFError:
                pass

    return exit_code


def main(argv: Sequence[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    return run_review(args)


if __name__ == "__main__":
    raise SystemExit(main())
