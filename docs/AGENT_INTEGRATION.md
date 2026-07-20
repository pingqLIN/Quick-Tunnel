# Agent and Process-Runner Integration

[Traditional Chinese reference](AGENT_INTEGRATION.zh-tw.md)

Use the CLI entry points, not Explorer or Finder Quick Actions, for Agent
integration. Quick Actions depend on interactive desktop state and are not a
portable headless interface.

## Required two-phase flow

Phase 1 performs a local preflight and opens no public tunnel:

```powershell
pwsh -NoLogo -NoProfile -File ./share-codex-review.ps1 `
  "D:\Project" -ValidateOnly -NoQrCode -Json
```

```zsh
python3 ./macos/share-codex-review.py "/path/to/project" \
  --validate-only --no-qr-code --json
```

The runner must require exit code `0`, a `validated` event, and a subsequent
`cleanup` event. It must then obtain explicit approval for unauthenticated
public exposure.

Phase 2 may run only after that approval:

```powershell
pwsh -NoLogo -NoProfile -File ./share-codex-review.ps1 `
  "D:\Project" -Yes -NoQrCode -Json
```

```zsh
python3 ./macos/share-codex-review.py "/path/to/project" \
  --yes --no-qr-code --json
```

Read stdout one NDJSON record at a time. The `public_ready` event contains the
URL while the process is still running. Keep the process attached, apply a
bounded duration, and treat the later `cleanup` event as the lifecycle close.
An `error` event or nonzero exit code is a failure. Never infer approval from
the presence of `--yes`; approval must come from the surrounding governed
workflow.

## Integration constraints

- Do not send source files, staging paths, logs, or secrets to unrelated
  services.
- Do not parse human-facing output when JSON mode is available.
- Do not log or persist the public URL longer than needed.
- Do not run a live Quick Tunnel in CI.
- Do not treat same-host public verification failure in a VM/NAT environment as
  proof that the external URL is unreachable.
- Do not use Quick Tunnel for high-sensitivity content; use an authenticated,
  organization-approved transport.

See the [threat model](THREAT_MODEL.md) for the complete security boundary and
NDJSON schema.
