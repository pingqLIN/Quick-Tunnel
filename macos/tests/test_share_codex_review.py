from __future__ import annotations

import importlib.util
import io
import json
import os
import plistlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


MACOS_DIRECTORY = Path(__file__).resolve().parents[1]
REPO_ROOT = MACOS_DIRECTORY.parent
MODULE_PATH = MACOS_DIRECTORY / "share-codex-review.py"
WORKFLOW_PATH = (
    MACOS_DIRECTORY
    / "templates"
    / "Share to Codex Review.workflow"
    / "Contents"
    / "document.wflow"
)
WORKFLOW_INFO_PATH = WORKFLOW_PATH.parent / "Info.plist"
MANAGER_PATH = MACOS_DIRECTORY / "manage-finder-quick-action.sh"
RUNNER_PATH = MACOS_DIRECTORY / "share-codex-review.command"
SETUP_PATH = MACOS_DIRECTORY / "finder-quick-action-setup.command"

SPEC = importlib.util.spec_from_file_location("share_codex_review_macos", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load module: {MODULE_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class InventoryTests(unittest.TestCase):
    def test_inventory_order_is_stable_for_case_and_unicode_variants(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            names = ("a.txt", "A.txt", "\u00e9.txt", "e\u0301.txt")
            for name in reversed(names):
                try:
                    (root / name).write_text(name, encoding="utf-8")
                except FileExistsError:
                    # Case-insensitive or normalization-insensitive filesystems
                    # may represent two spellings as one file.
                    pass

            first = MODULE.build_inventory(root, maximum_file_bytes=1024)
            second = MODULE.build_inventory(root, maximum_file_bytes=1024)

            expected = sorted(
                (entry.relative_path for entry in first.files),
                key=MODULE.path_sort_key,
            )
            self.assertEqual(
                [entry.relative_path for entry in first.files],
                expected,
            )
            self.assertEqual(first.files, second.files)

    def test_inventory_excludes_sensitive_dependency_and_oversized_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "main.py").write_text("print('safe')", encoding="utf-8")
            (root / ".env").write_text("NOT_A_REAL_SECRET=value", encoding="utf-8")
            (root / ".git").mkdir()
            (root / ".git" / "config").write_text("ignored", encoding="utf-8")
            (root / "private").mkdir()
            (root / "private" / "notes.txt").write_text("ignored", encoding="utf-8")
            (root / "large.bin").write_bytes(b"12345")

            inventory = MODULE.build_inventory(
                root,
                maximum_file_bytes=4,
                additional_excludes=("private",),
            )

            self.assertEqual(
                [entry.relative_path for entry in inventory.files],
                [],
            )
            self.assertGreaterEqual(inventory.excluded_count, 3)
            self.assertEqual(inventory.oversized_count, 2)

    def test_inventory_keeps_safe_files_and_skips_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "safe.txt").write_text("safe", encoding="utf-8")
            symlink_path = root / "linked.txt"
            try:
                symlink_path.symlink_to(root / "safe.txt")
            except OSError:
                symlink_path = None

            inventory = MODULE.build_inventory(root, maximum_file_bytes=1024)

            self.assertEqual(
                [entry.relative_path for entry in inventory.files],
                ["safe.txt"],
            )
            if symlink_path is not None:
                self.assertGreaterEqual(inventory.excluded_count, 1)

    def test_secret_scan_reports_only_matching_file_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            safe_path = root / "safe.txt"
            secret_path = root / "credential.txt"
            safe_path.write_text("safe", encoding="utf-8")
            secret_path.write_text("ghp_" + ("A" * 36), encoding="utf-8")
            entries = (
                MODULE.InventoryEntry(
                    safe_path,
                    "safe.txt",
                    safe_path.stat().st_size,
                    MODULE.hash_regular_file(safe_path, "safe.txt")[1],
                ),
                MODULE.InventoryEntry(
                    secret_path,
                    "credential.txt",
                    secret_path.stat().st_size,
                    MODULE.hash_regular_file(secret_path, "credential.txt")[1],
                ),
            )

            self.assertEqual(
                MODULE.find_potential_secret_paths(entries),
                ("credential.txt",),
            )

    def test_secret_scan_supports_utf8_utf16_and_malformed_utf8(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            fake_secret = "ghp_" + ("C" * 36)
            paths = (
                root / "utf8.txt",
                root / "utf16.txt",
                root / "mixed.txt",
            )
            paths[0].write_text(fake_secret, encoding="utf-8")
            paths[1].write_text(fake_secret, encoding="utf-16")
            paths[2].write_bytes(
                b"prefix\xff" + fake_secret.encode("ascii")
            )

            for path in paths:
                length, content_hash = MODULE.hash_regular_file(path, path.name)
                entry = MODULE.InventoryEntry(
                    path,
                    path.name,
                    length,
                    content_hash,
                )
                self.assertTrue(MODULE.contains_potential_secret(entry))

    def test_staging_stops_if_a_source_file_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source_path = root / "source.txt"
            destination_path = root / "stage" / "source.txt"
            source_path.write_text("first", encoding="utf-8")
            entry = MODULE.InventoryEntry(
                source_path,
                "source.txt",
                source_path.stat().st_size,
                MODULE.hash_regular_file(source_path, "source.txt")[1],
            )
            source_path.write_text("other", encoding="utf-8")

            with self.assertRaisesRegex(
                RuntimeError,
                "Source file changed during staging",
            ):
                MODULE.copy_inventory_entry(entry, root, destination_path)

    @unittest.skipUnless(
        os.open in os.supports_dir_fd
        and getattr(os, "O_NOFOLLOW", 0) != 0
        and getattr(os, "O_DIRECTORY", 0) != 0,
        "descriptor-relative no-follow traversal requires a Unix-like host",
    )
    def test_staging_rejects_an_ancestor_symlink_swap(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            root = base / "source"
            nested = root / "nested"
            outside = base / "outside"
            nested.mkdir(parents=True)
            outside.mkdir()
            source_path = nested / "review.txt"
            source_path.write_text("inside", encoding="utf-8")
            (outside / "review.txt").write_text("outside", encoding="utf-8")
            entry = MODULE.build_inventory(root, 1024).files[0]
            nested.rename(root / "nested-original")
            nested.symlink_to(outside, target_is_directory=True)

            with self.assertRaisesRegex(
                RuntimeError,
                "Source path escaped or crossed a symlink",
            ):
                MODULE.copy_inventory_entry(
                    entry,
                    root,
                    base / "stage" / "review.txt",
                )


class IndexTests(unittest.TestCase):
    def test_index_name_collision_is_case_insensitive(self) -> None:
        self.assertEqual(
            MODULE.choose_index_file_name(
                (
                    "__CODEX_REVIEW__.HTML",
                    "__codex_review_1.html",
                )
            ),
            "__codex_review_2.html",
        )

    def test_review_index_escapes_display_and_url_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            destination = Path(temporary_directory) / "index.html"
            MODULE.write_review_index(
                destination,
                (
                    MODULE.SharedFile(
                        original_relative_path="a <b>/space name.txt",
                        shared_relative_path="a <b>/space name.txt",
                        length=12,
                    ),
                ),
                source_folder_name="<project>",
                excluded_count=1,
                oversized_count=2,
            )
            content = destination.read_text(encoding="utf-8")

            self.assertIn("&lt;project&gt;", content)
            self.assertIn("a%20%3Cb%3E/space%20name.txt", content)
            self.assertIn("a &lt;b&gt;/space name.txt", content)
            self.assertNotIn("<project>", content)

    def test_review_index_bytes_do_not_depend_on_input_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first_path = root / "first.html"
            second_path = root / "second.html"
            files = (
                MODULE.SharedFile("a.txt", "a.txt", 1),
                MODULE.SharedFile("A.txt", "A.txt", 2),
                MODULE.SharedFile("\u00e9.txt", "\u00e9.txt", 3),
            )

            MODULE.write_review_index(first_path, files, "sample", 0, 0)
            MODULE.write_review_index(
                second_path,
                tuple(reversed(files)),
                "sample",
                0,
                0,
            )

            self.assertEqual(first_path.read_bytes(), second_path.read_bytes())


class TunnelTests(unittest.TestCase):
    def test_machine_error_redacts_paths_and_sensitive_values(self) -> None:
        sensitive_path = Path("/private/example/project")
        message = (
            f"Unable to inspect {sensitive_path}; "
            "token=example-sensitive-value"
        )
        redacted = MODULE.redact_machine_error(message, (sensitive_path,))
        self.assertNotIn(str(sensitive_path), redacted)
        self.assertNotIn("example-sensitive-value", redacted)
        self.assertIn("[PATH]", redacted)
        self.assertIn("[REDACTED]", redacted)

    def test_headless_wait_ignores_standard_input(self) -> None:
        with mock.patch.object(MODULE.time, "sleep") as sleep:
            self.assertTrue(
                MODULE.wait_for_stop(1, allow_standard_input=False)
            )
        sleep.assert_called_once_with(60)

    def test_public_json_event_contract(self) -> None:
        output = io.StringIO()
        MODULE.write_review_event(
            output,
            event="public_ready",
            mode="public",
            public_url="https://example.trycloudflare.com/__index__.html",
            expires_at="2026-07-19T13:00:00+00:00",
            server_pid=101,
            tunnel_pid=202,
            staging_root=Path("/tmp/staging"),
            error=None,
        )

        event = json.loads(output.getvalue())
        self.assertEqual(event["schema_version"], 1)
        self.assertEqual(event["event"], "public_ready")
        self.assertEqual(event["mode"], "public")
        self.assertEqual(event["server_pid"], 101)
        self.assertEqual(event["tunnel_pid"], 202)
        self.assertTrue(event["public_url"].startswith("https://"))

    def test_retry_requires_server_and_unmarshal_signals(self) -> None:
        retryable = (
            'status_code="500" Error unmarshaling QuickTunnel response '
            "error code: 1101"
        )
        rate_limited = (
            'status_code="429" Error unmarshaling QuickTunnel response'
        )
        configuration_error = "failed to parse configuration"

        self.assertTrue(MODULE.is_retryable_quick_tunnel_failure(retryable))
        self.assertFalse(MODULE.is_retryable_quick_tunnel_failure(rate_limited))
        self.assertFalse(
            MODULE.is_retryable_quick_tunnel_failure(configuration_error)
        )

    def test_diagnostic_summary_redacts_sensitive_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            log_path = Path(temporary_directory) / "tunnel.log"
            log_path.write_text(
                "ERR request failed token=Bearer example-sensitive-value\n",
                encoding="utf-8",
            )

            diagnostics = MODULE.get_tunnel_error_summary((log_path,))

            self.assertEqual(len(diagnostics), 1)
            self.assertIn("token=[REDACTED]", diagnostics[0])
            self.assertNotIn("example-sensitive-value", diagnostics[0])


class IntegrationTests(unittest.TestCase):
    def test_json_error_event_redacts_local_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            missing_path = Path(temporary_directory) / "missing-folder"
            result = subprocess.run(
                (
                    sys.executable,
                    str(MODULE_PATH),
                    str(missing_path),
                    "--validate-only",
                    "--no-qr-code",
                    "--json",
                ),
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            event = json.loads(result.stdout.strip())
            self.assertEqual(event["event"], "error")
            self.assertNotIn(str(missing_path), event["error"])
            self.assertIn("[PATH]", event["error"])

    def test_validate_only_json_contract_and_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_root = Path(temporary_directory)
            (source_root / "review.txt").write_text("safe", encoding="utf-8")
            environment = os.environ.copy()
            environment["PYTHONDONTWRITEBYTECODE"] = "1"

            result = subprocess.run(
                (
                    sys.executable,
                    str(MODULE_PATH),
                    str(source_root),
                    "--validate-only",
                    "--no-qr-code",
                    "--json",
                ),
                cwd=REPO_ROOT,
                env=environment,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            events = tuple(
                json.loads(line)
                for line in result.stdout.splitlines()
                if line.strip()
            )
            self.assertEqual(
                tuple(event["event"] for event in events),
                ("validated", "cleanup"),
            )
            required_fields = {
                "schema_version",
                "event",
                "mode",
                "public_url",
                "expires_at",
                "server_pid",
                "tunnel_pid",
                "staging_root",
                "error",
            }
            for event in events:
                self.assertEqual(set(event), required_fields)
                self.assertEqual(event["schema_version"], 1)
                self.assertEqual(event["mode"], "validate_only")
                self.assertIsNone(event["public_url"])
                self.assertIsNone(event["tunnel_pid"])
                self.assertIsNone(event["error"])
            self.assertFalse(Path(events[-1]["staging_root"]).exists())

    def test_validate_only_runs_without_public_tunnel(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_root = Path(temporary_directory)
            (source_root / "review.txt").write_text(
                "safe review content",
                encoding="utf-8",
            )
            environment = os.environ.copy()
            environment["PYTHONDONTWRITEBYTECODE"] = "1"

            result = subprocess.run(
                (
                    sys.executable,
                    str(MODULE_PATH),
                    str(source_root),
                    "--validate-only",
                    "--no-qr-code",
                ),
                cwd=REPO_ROOT,
                env=environment,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Local read-only server verified:", result.stdout)
            self.assertIn(
                "Validation complete. No public tunnel was opened.",
                result.stdout,
            )
            self.assertNotIn("Share URL:", result.stdout)

    def test_public_confirmation_can_cancel_before_cloudflared(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_root = Path(temporary_directory)
            (source_root / "review.txt").write_text("safe", encoding="utf-8")
            environment = os.environ.copy()
            environment["PYTHONDONTWRITEBYTECODE"] = "1"

            result = subprocess.run(
                (
                    sys.executable,
                    str(MODULE_PATH),
                    str(source_root),
                    "--no-qr-code",
                ),
                cwd=REPO_ROOT,
                env=environment,
                input="CANCEL\n",
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("PUBLIC SHARING WARNING", result.stdout)
            self.assertIn(
                "Sharing cancelled. No public tunnel was opened.",
                result.stdout,
            )
            self.assertNotIn("Share URL:", result.stdout)

    def test_secret_detection_stops_before_local_server(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_root = Path(temporary_directory)
            fake_secret = "ghp_" + ("A" * 36)
            (source_root / "credential.txt").write_text(
                fake_secret,
                encoding="utf-8",
            )
            environment = os.environ.copy()
            environment["PYTHONDONTWRITEBYTECODE"] = "1"

            result = subprocess.run(
                (
                    sys.executable,
                    str(MODULE_PATH),
                    str(source_root),
                    "--validate-only",
                ),
                cwd=REPO_ROOT,
                env=environment,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("credential.txt", result.stderr)
            self.assertNotIn(fake_secret, result.stdout + result.stderr)
            self.assertNotIn("Local read-only server verified:", result.stdout)

    def test_automator_workflow_is_valid_and_accepts_finder_paths(self) -> None:
        with WORKFLOW_INFO_PATH.open("rb") as info_file:
            workflow_info = plistlib.load(info_file)
        with WORKFLOW_PATH.open("rb") as workflow_file:
            workflow = plistlib.load(workflow_file)

        service = workflow_info["NSServices"][0]
        self.assertEqual(service["NSMessage"], "runWorkflowAsService")
        self.assertEqual(service["NSSendFileTypes"], ["public.item"])
        self.assertEqual(service["NSIconName"], "NSActionTemplate")
        self.assertEqual(
            service["NSRequiredContext"]["NSApplicationIdentifier"],
            "com.apple.finder",
        )
        self.assertEqual(
            service["NSMenuItem"]["default"],
            "Share to Codex Review",
        )

        metadata = workflow["workflowMetaData"]
        self.assertEqual(
            metadata["workflowTypeIdentifier"],
            "com.apple.Automator.servicesMenu",
        )
        self.assertEqual(
            metadata["serviceInputTypeIdentifier"],
            "com.apple.Automator.fileSystemObject",
        )
        parameters = workflow["actions"][0]["action"]["ActionParameters"]
        self.assertEqual(parameters["shell"], "/bin/zsh")
        self.assertEqual(parameters["inputMethod"], 1)
        self.assertIn(
            "QuickTunnelReviewShare/launch-from-finder.sh",
            parameters["COMMAND_STRING"],
        )

        manager = MANAGER_PATH.read_text(encoding="utf-8")
        runner = RUNNER_PATH.read_text(encoding="utf-8")
        self.assertIn("/System/Library/CoreServices/pbs", manager)
        self.assertIn('"$pbs_path" -update', manager)
        self.assertIn("Python 3.9 or newer is required", manager)
        self.assertIn("Unavailable (non-blocking)", manager)
        self.assertIn("Finder may discover the workflow asynchronously", manager)
        self.assertNotIn("rm -rf", manager)
        self.assertIn("sys.version_info >= (3, 9)", runner)

    def test_finder_setup_exposes_doctor(self) -> None:
        setup_text = SETUP_PATH.read_text(encoding="utf-8")
        self.assertIn('print "  4. Run doctor"', setup_text)
        self.assertIn('/bin/zsh "$manager" doctor', setup_text)
        self.assertIn('read "choice?Select [1-5]: "', setup_text)


if __name__ == "__main__":
    unittest.main()
