# Quick Tunnel Review Share

Quick Tunnel Review Share creates a temporary, filtered snapshot of a local
folder and publishes it through a Cloudflare Quick Tunnel for short-lived code
review. The source folder is never served directly.

[Traditional Chinese reference](README.zh-tw.md)

## Requirements

- Windows with PowerShell 7 (`pwsh.exe`)
- Python 3
- `cloudflared`
- Optional: `qrencode` for a terminal QR code

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

## Explorer context menu

Double-click `context-menu-setup.cmd`, choose **Install**, and type `INSTALL`.
The command is installed for the current Windows user only. On Windows 11 it
may appear under **Show more options**.

To remove it:

```powershell
.\manage-context-menu.ps1 -Action Uninstall
```

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
