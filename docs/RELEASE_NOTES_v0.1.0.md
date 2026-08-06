# Quick Tunnel Review Share v0.1.0

First tagged release of Quick Tunnel Review Share.

Quick Tunnel Review Share creates a temporary, filtered snapshot of a local
folder and shares that isolated snapshot through a time-limited Cloudflare Quick
Tunnel. The original source directory is never served directly.

## Highlights

- Windows PowerShell and macOS Python command-line workflows.
- Windows Explorer context-menu and macOS Finder Quick Action integration,
  both labelled **Make Q-Tunnel**.
- Filtered staging snapshots with source-content hashing and mutation detection.
- Conservative secret scanning and exclusion rules before public sharing.
- A loopback-only local safe server with inert MIME handling, restrictive
  security headers, and path confinement.
- Explicit `SHARE` approval before a public tunnel opens.
- Bounded retry diagnostics for transient Cloudflare Quick Tunnel failures.
- Versioned NDJSON lifecycle output via Windows `-Json` and macOS `--json`.
- Cross-platform test coverage and GitHub Actions checks.
- MIT License (`SPDX-License-Identifier: MIT`).

## Compatibility

- Windows: PowerShell 7 and Python 3.9 or newer.
- macOS: macOS 14 or newer, Python 3.9 or newer, and `cloudflared`.
- `cloudflared` should remain within Cloudflare's supported release window.

## Important safety note

Quick Tunnel URLs are temporary but unauthenticated. Anyone who obtains the URL
can access the filtered snapshot while the tunnel is running. Review the
selected folder, use the default filters, and add project-specific exclusions
before sharing.
