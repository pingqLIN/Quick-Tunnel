# Quick Tunnel Review Share

Quick Tunnel Review Share creates a temporary, filtered snapshot of a local
folder and publishes it through a Cloudflare Quick Tunnel for short-lived code
review. The source folder is never served directly.

[Traditional Chinese reference](README.zh-tw.md)

Project documentation: [threat model](docs/THREAT_MODEL.md),
[Agent integration](docs/AGENT_INTEGRATION.md),
[security policy](SECURITY.md), [contributing guide](CONTRIBUTING.md), and
[changelog](CHANGELOG.md).

## Requirements

| Component | Documented support | Enforced check | Tested evidence |
| --- | --- | --- | --- |
| Windows | PowerShell 7; Python 3.9+ | `#requires` and runtime Python check | PowerShell 7.6.3 and Python 3.14.6 on 2026-07-19 |
| macOS | macOS 14+ Homebrew path; Python 3.9+ | wrapper and Finder doctor check Python 3.9+ | macOS 15.7.7 x86_64 and Python 3.9.6 on 2026-07-19 |
| `cloudflared` | A release still inside Cloudflare's one-year support window | executable presence; Finder doctor also reports the version | 2026.6.1 in the macOS VM and 2026.7.1 on Windows |
| `qrencode` | Optional | no hard requirement | 4.1.1 in the macOS VM |

There is no invented numeric `cloudflared` minimum: Cloudflare publishes a
one-year release-support policy, while this project enforces only the CLI
capabilities it uses. Keep `cloudflared` updated within that support window.
The Finder path additionally requires built-in zsh, Terminal, Finder,
Automator, AppleScript, and `plutil`.

See the [macOS guide](macos/README.md) for Finder Quick Action installation,
feature parity, and verification.

## Usage

```powershell
.\share-codex-review.ps1 "D:\Projects\MyProject"
```

Use `-ValidateOnly` to build and verify the filtered local snapshot without
opening a public tunnel:

```powershell
.\share-codex-review.ps1 "D:\Projects\MyProject" -ValidateOnly
```

The default public lifetime is 30 minutes. Change it with
`-DurationMinutes`, or press Enter to stop early.

Common Windows options:

| Purpose | Option |
| --- | --- |
| Change lifetime | `-DurationMinutes 10` |
| Select a local port | `-Port 8080` |
| Limit copied file size | `-MaxFileSizeMB 25` |
| Add a wildcard exclusion | `-AdditionalExclude "private/*"` |
| Disable QR output | `-NoQrCode` |
| Skip the `SHARE` prompt | `-Yes` |
| Change retry count | `-QuickTunnelAttempts 3` |
| Change retry base delay | `-QuickTunnelRetryBaseSeconds 5` |
| Emit versioned NDJSON | `-Json` |

`-Yes` creates an unauthenticated public endpoint without the interactive
confirmation. Use it only inside an already approved workflow.

On macOS:

~~~zsh
python3 ./macos/share-codex-review.py "/path/to/MyProject"
~~~

Build and verify the filtered snapshot without opening a public tunnel:

~~~zsh
python3 ./macos/share-codex-review.py "/path/to/MyProject" --validate-only
~~~

## Machine-readable lifecycle

Use `-Json` on Windows or `--json` on macOS for versioned NDJSON lifecycle
events. Validate-only emits `validated` and `cleanup`; public mode emits
`public_ready` while the URL is live and `cleanup` after processes and staging
are removed. Errors emit `error` and return a nonzero exit code.

JSON public mode requires `-Yes` or `--yes` so stdout cannot block on a prompt.
The version 1 fields are `schema_version`, `event`, `mode`, `public_url`,
`expires_at`, `server_pid`, `tunnel_pid`, `staging_root`, and `error`. The
explicit JSON option permits disclosure of the local `staging_root`; do not
forward that field unnecessarily. See the
[Agent integration contract](docs/AGENT_INTEGRATION.md).

## Windows Explorer context menu

Double-click `context-menu-setup.cmd`, choose **Install**, and type `INSTALL`.
The command is installed for the current Windows user only. On Windows 11 it
may appear under **Show more options**.

To remove it:

```powershell
.\manage-context-menu.ps1 -Action Uninstall
```

## macOS Finder Quick Action

Install the per-user Finder Quick Action:

~~~zsh
/bin/zsh ./macos/manage-finder-quick-action.sh install
~~~

Run the non-mutating compatibility and version check first, or choose
**Run doctor** from `finder-quick-action-setup.command`:

~~~zsh
/bin/zsh ./macos/manage-finder-quick-action.sh doctor
~~~

Select one folder in Finder, then choose **Quick Actions > Share to Codex
Review**. Removal is recoverable: installed files are moved into sibling
`.del` folders instead of being permanently erased.

## Safety model

- Copies permitted files into an isolated temporary staging directory.
- Excludes common dependency, VCS, environment, credential, and key paths.
- Blocks high-signal secret formats before opening the tunnel.
- Skips reparse points and files above the configured size limit.
- Serves source-controlled HTML, SVG, scripts, and markup as inert plain text.
- Adds restrictive browser security headers and disables caching.
- Binds the local origin to `127.0.0.1` only.
- Requires explicit `SHARE` confirmation unless `-Yes` is supplied.
- Stops the local server and tunnel and removes staging files on exit.

The secret scan is intentionally conservative and cannot guarantee that every
credential or private datum has been detected. Review the selected folder and
use `-AdditionalExclude` for project-specific private paths before sharing.
It scans only configured text extensions whose staged size is at most 2 MiB;
larger or unknown-format files may still be copied when they are under the
separate copy-size limit. Remote inert rendering also does not make a downloaded
file safe to execute.

Cleanup is guaranteed for normal exit and handled failures. Force-killing the
process, terminating the host, or an operating-system crash can leave temporary
files behind. Follow the [threat model](docs/THREAT_MODEL.md) for recovery and
residual-risk guidance.

## Quick Tunnel lifecycle

The Quick Tunnel is created only after local validation and explicit approval.
The terminal displays the public URL, process IDs, verification result, and
scheduled expiration time. When the lifetime expires, the tunnel is stopped
and temporary files are removed. Context-menu launches keep the completion
message visible until acknowledged. Transient Cloudflare-side `500/1101`
Quick Tunnel creation failures are retried up to three times with exponential
backoff; configuration errors and rate-limit responses are not retried.

Cloudflare Quick Tunnels are unauthenticated, temporary development endpoints.
Anyone with the generated URL can access the filtered snapshot while the
process is running.

## Developer verification

```powershell
./windows/tests/test-share-codex-review.ps1
python -m unittest discover -s tests -v
```

```zsh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s macos/tests -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

GitHub Actions runs the Windows suite, macOS Python and native syntax checks,
shared safe-server tests, and a current-Python compatibility job. CI never opens
a public tunnel or installs desktop integrations.

## License

Quick Tunnel Review Share is licensed under the
[MIT License](LICENSE) (`SPDX-License-Identifier: MIT`).
