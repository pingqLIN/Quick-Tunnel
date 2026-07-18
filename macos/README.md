# Quick Tunnel Review Share for macOS

This is the macOS counterpart to the Windows PowerShell workflow. It creates
the same filtered snapshot, serves active source formats as inert content, and
opens a time-limited Cloudflare Quick Tunnel only after explicit confirmation.

[Traditional Chinese reference](README.zh-tw.md)

## Supported environment

- macOS 14 Sonoma or newer for the
  [supported Homebrew dependency path](https://docs.brew.sh/Installation)
- Python 3.9 or newer
- `cloudflared`
- Built-in zsh, Terminal, Finder, and Automator
- Optional: `qrencode` for a terminal QR code

[Cloudflare's macOS download instructions](https://developers.cloudflare.com/tunnel/downloads/)
document Homebrew as the standard installation route:

~~~zsh
brew install python cloudflared
brew install qrencode
~~~

The second command is optional. Installing dependencies changes the machine and
is intentionally not performed by this repository.

## Validate before sharing

Run the complete local snapshot and safe-server flow without creating a public
tunnel:

~~~zsh
python3 ./macos/share-codex-review.py "/path/to/project" \
  --validate-only \
  --no-qr-code
~~~

## Share from Terminal

~~~zsh
python3 ./macos/share-codex-review.py "/path/to/project"
~~~

The script prints a public-sharing warning and requires the exact word `SHARE`
before starting `cloudflared`. The default lifetime is 30 minutes. Press Return
to stop earlier.

Common options:

| Purpose | Option |
| --- | --- |
| Change lifetime | `--duration-minutes 10` |
| Select a local port | `--port 8080` |
| Limit copied file size | `--max-file-size-mb 25` |
| Add a wildcard exclusion | `--additional-exclude "private/*"` |
| Disable the QR code | `--no-qr-code` |
| Skip the `SHARE` prompt | `--yes` |
| Change retry count | `--quick-tunnel-attempts 3` |
| Change retry base delay | `--quick-tunnel-retry-base-seconds 5` |

`--yes` opens a public endpoint without the interactive confirmation and should
be used only in an already approved workflow.

## Finder Quick Action

Install the current-user runtime and Quick Action:

~~~zsh
/bin/zsh ./macos/manage-finder-quick-action.sh install
~~~

The installer requires the exact word `INSTALL`. It copies the runtime to:

~~~text
~/Library/Application Support/QuickTunnelReviewShare
~~~

It installs the Automator workflow at:

~~~text
~/Library/Services/Share to Codex Review.workflow
~~~

Before installing on another Mac, run the non-mutating compatibility check:

~~~zsh
/bin/zsh ./macos/manage-finder-quick-action.sh doctor
~~~

It verifies macOS, Python 3.9 or newer, the required system tools, both workflow
property lists, and the Python entry point. The installer refreshes Finder's
Services registry when the version-specific registry helper is available. If
that private helper is missing or behaves differently, normal Finder discovery
remains supported and the unconfirmed registry state is reported without
misclassifying the copied installation as damaged.

Select exactly one folder in Finder and choose **Quick Actions > Share to Codex
Review**. A Terminal window opens so the warning, URL, retry diagnostics,
lifetime, and cleanup remain visible.

On first use, macOS may ask whether Finder may control Terminal and whether
Python may accept local-network connections. Those permissions are needed for
the Finder launch and loopback-only preview respectively; they do not bypass the
exact `SHARE` confirmation required before a public tunnel opens.

If the action is hidden, enable it under **System Settings > Privacy & Security
> Extensions > Finder**. [Apple's Quick Action guide](https://support.apple.com/guide/automator/use-quick-action-workflows-aut73234890a/mac)
documents Finder file input as a requirement for Finder Quick Actions; this
workflow therefore rejects files and multiple selections. Finder has no exact
Automator equivalent to Windows' folder background menu, so select the folder
itself before running the action.

Show installation status:

~~~zsh
/bin/zsh ./macos/manage-finder-quick-action.sh status
~~~

Remove the integration:

~~~zsh
/bin/zsh ./macos/manage-finder-quick-action.sh uninstall
~~~

Removal requires the exact word `REMOVE`. The workflow and runtime are moved to
sibling `.del` folders with timestamped names, so removal remains recoverable.
Uninstalling does not reset macOS privacy decisions. Revoke the Finder-to-
Terminal or Python local-network permission separately in System Settings if
the integration will no longer be used.

## Feature parity

| Windows behavior | macOS counterpart | Status |
| --- | --- | --- |
| Filtered temporary copy | Python inventory and staging directory | Implemented |
| VCS, dependency, credential, and key exclusions | Same names and wildcard patterns | Implemented |
| Reparse-point protection | Symlinks are never followed or copied | Implemented |
| High-signal secret scan | Same credential pattern families | Implemented |
| Inert source serving | Shared `safe-review-server.py` | Implemented |
| Loopback-only local origin | Binds only to `127.0.0.1` | Implemented |
| Explicit public approval | Exact `SHARE` confirmation | Implemented |
| Isolated Quick Tunnel config | Temporary empty config file | Implemented |
| Transient 500/1101 retry | Bounded exponential backoff | Implemented |
| No retry for 429/config errors | Combined failure-signal classifier | Implemented |
| Public URL verification | HTTP 200, content type, and marker check | Implemented |
| QR output | Optional `qrencode` integration | Implemented |
| Enter or lifetime stop | Terminal Return key or timeout | Implemented |
| Child and temp cleanup | `finally`-guarded process and directory cleanup | Implemented |
| Explorer context menu | Finder Automator Quick Action | Implemented equivalent |
| Install/status/uninstall | Per-user Finder integration manager | Implemented |

## Safety boundaries

- The source directory is never served directly.
- Symlinks, common secret files, VCS data, dependencies, and oversized files are
  excluded. Secret scanning runs against the exact staged bytes before any
  server starts.
- Only the isolated copy is served.
- HTML, SVG, JavaScript, and other active source formats are served as inert
  `text/plain` by the shared safe server.
- Browser caching is disabled and restrictive security headers are applied.
- The local server binds only to `127.0.0.1`.
- The Quick Tunnel is unauthenticated. Anyone with the URL can access the
  filtered snapshot until the process stops.
- Public verification runs from the same Mac. A VM or NAT policy may prevent
  that Mac from reaching its own `trycloudflare.com` URL even when an external
  client can reach it. If the self-check warns, verify from the intended
  external client before relying on the URL.
- Secret scanning is conservative and cannot prove that a folder contains no
  private information. Review the folder and add project-specific exclusions.

## Developer verification

Cross-platform core tests:

~~~zsh
python3 -m unittest discover -s macos/tests -v
~~~

For a clean macOS user with no existing Quick Tunnel integration, the governed
repeatability check runs the static and unit checks plus two complete
install/status/byte-comparison/uninstall cycles:

~~~zsh
/bin/zsh ./macos/tests/run-repeatability-tests.zsh
~~~

The script refuses to overwrite an existing or partial installation. Test
removals use timestamped `.del` folders and remain recoverable. A pass confirms
repeatability on the Mac that ran the test; it is not evidence for untested
macOS releases, CPU architectures, or managed-device policies.

Native VM evidence recorded on 2026-07-19 used macOS 15.7.7 x86_64, Python
3.9.6, `cloudflared` 2026.6.1, and `qrencode` 4.1.1. The filtered public URL
returned HTTP 200 and the review marker from an external host; QR generation,
automatic expiry, and process cleanup passed. The VM could not reach its own
public URL through its NAT path, so the same-Mac self-check correctly remained a
warning rather than being reported as verified.

On macOS, also run:

~~~zsh
/bin/zsh -n macos/share-codex-review.command
/bin/zsh -n macos/launch-from-finder.sh
/bin/zsh -n macos/manage-finder-quick-action.sh
/bin/zsh -n macos/finder-quick-action-setup.command
plutil -lint \
  "macos/templates/Share to Codex Review.workflow/Contents/Info.plist"
plutil -lint \
  "macos/templates/Share to Codex Review.workflow/Contents/document.wflow"
/bin/zsh -n macos/tests/run-repeatability-tests.zsh
~~~

Then install the Quick Action and exercise `--validate-only` from Finder before
approving a real public tunnel.
