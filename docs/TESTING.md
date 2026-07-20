# Testing and Verification

[Traditional Chinese reference](TESTING.zh-tw.md)

This document separates reproducible test commands from historical environment
evidence. A historical pass applies only to the tested revision and does not
prove that a later working tree, operating-system release, or runner image
still passes.

## Local checks

On Windows with PowerShell 7 and Python 3.9 or newer:

```powershell
./windows/tests/test-share-codex-review.ps1
python -m unittest discover -s tests -v
python -m py_compile safe-review-server.py macos/share-codex-review.py `
  macos/tests/test_share_codex_review.py tests/test_safe_review_server.py
```

On macOS with Python 3.9 or newer:

```zsh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s macos/tests -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
zsh -n macos/share-codex-review.command
zsh -n macos/launch-from-finder.sh
zsh -n macos/manage-finder-quick-action.sh
zsh -n macos/finder-quick-action-setup.command
zsh -n macos/tests/run-repeatability-tests.zsh
plutil -lint "macos/templates/Share to Codex Review.workflow/Contents/Info.plist"
plutil -lint "macos/templates/Share to Codex Review.workflow/Contents/document.wflow"
```

The Finder repeatability test installs and removes current-user integration.
Run it only through an approved machine-mutation gate. It refuses to overwrite
an existing or partial installation, and removals remain recoverable in sibling
`.del` directories.

## Continuous integration

`ci.yml` runs Windows regression tests, the macOS Python and shell/property-list
checks, shared safe-server tests, and the current Python compatibility job.
`dependency-review.yml` examines dependency changes in pull requests. Local
passes do not substitute for an actual GitHub Actions result on the committed
revision.

CI never opens a public tunnel and does not run the Finder installation cycle.

## Historical native macOS evidence

The published commit `dcb3dc8` was exercised on 2026-07-19 with macOS 15.7.7
x86_64, Python 3.9.6, `cloudflared` 2026.6.1, and `qrencode` 4.1.1. The filtered
public URL returned HTTP 200 and the review marker from an external host; QR
generation, automatic expiry, and cleanup passed. The VM could not reach its
own public URL through its NAT path, so the same-Mac self-check remained a
warning.

This evidence predates the current uncommitted candidate changes. Native macOS
validation of those changes remains unknown until the exact candidate revision
is tested on macOS.
