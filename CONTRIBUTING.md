# Contributing to Quick Tunnel Review Share

[Traditional Chinese reference](CONTRIBUTING.zh-tw.md)

Thanks for helping improve Quick Tunnel Review Share. English documentation is
authoritative; important operator-facing changes should include an updated
Traditional Chinese `.zh-tw.md` companion.

## Before opening a change

- Keep the source-folder boundary intact: only a filtered staging snapshot may
  be served.
- Never add real credentials, private URLs, cookies, or production data to
  source, tests, fixtures, issues, or logs.
- Keep public sharing behind the exact `SHARE` confirmation unless the caller
  explicitly selects `-Yes` or `--yes` in an already approved workflow.
- Do not use a live Quick Tunnel as part of automated tests.
- Report suspected vulnerabilities through the private process in
  [SECURITY.md](SECURITY.md), not a public issue.

## Local verification

On Windows with PowerShell 7 and Python 3.9 or newer:

```powershell
./windows/tests/test-share-codex-review.ps1
python -m unittest discover -s tests -v
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
plutil -lint \
  "macos/templates/Share to Codex Review.workflow/Contents/Info.plist"
plutil -lint \
  "macos/templates/Share to Codex Review.workflow/Contents/document.wflow"
```

The Finder repeatability test changes the current user's Library and therefore
has its own confirmation gate. It is not part of the default CI workflow.

## Pull requests

Describe the behavior change, safety impact, rollback path, and verification
performed. The pull request template records these checks consistently. Update
[CHANGELOG.md](CHANGELOG.md) for user-visible changes. Changes
to exclusions, secret scanning, staging, public approval, JSON events, cleanup,
or safe-server headers must update the relevant tests and the
[threat model](docs/THREAT_MODEL.md).

CI must pass on Windows and macOS before merge. A green local run does not
substitute for an actual GitHub Actions result.

See [testing and verification](docs/TESTING.md) for the complete command set and
evidence boundaries.
