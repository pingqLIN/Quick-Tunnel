# Changelog

[Traditional Chinese reference](CHANGELOG.zh-tw.md)

All notable changes to this project are recorded here. The project has not yet
published a tagged release.

## Unreleased

### Added

- Versioned NDJSON lifecycle output for Windows `-Json` and macOS `--json`.
- Windows regression coverage for exclusions, encoding tolerance, fail-closed
  reads, staged-byte scanning, source mutation, reparse traversal, cancellation,
  cleanup, and JSON contracts.
- Shared safe-server HTTP tests for inert MIME types, security headers, unknown
  binary content, and path confinement.
- Cross-platform GitHub Actions checks on Windows, macOS, and current Python.
- Pull request and issue templates, dependency review, and Dependabot updates
  for pinned GitHub Actions.
- Governance, security, threat-model, and Agent integration documentation.
- Dedicated testing, release-policy, and GitHub-settings documentation.
- Finder setup access to the existing non-mutating `doctor` check.
- MIT licensing with the SPDX identifier `MIT`.

### Changed

- Windows and macOS staging now hash source content and reject equal-length
  mutations before serving the snapshot.
- Windows scans the hash-verified staged bytes and fails closed when a candidate
  cannot be inspected.
- `.cmd` files are served as inert text, and `.log` files are included in the
  secret-scan extension set.
- The shared safe server now rejects non-loopback bind addresses at its CLI
  boundary.
- Windows now enforces Python 3.9 or newer.

## 2026-07-18

- Added the macOS CLI, Finder Quick Action, recoverable installer, tests, and
  English/Traditional Chinese documentation.

## 2026-07-16

- Added the Windows filtered snapshot, safe local server, Cloudflare Quick
  Tunnel workflow, Explorer context menu, retry diagnostics, and core docs.
