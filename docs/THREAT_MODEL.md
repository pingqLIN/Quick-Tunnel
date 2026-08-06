# Threat Model

[Traditional Chinese reference](THREAT_MODEL.zh-tw.md)

## Purpose and scope

Quick Tunnel Review Share gives a reviewer temporary access to a filtered copy
of a local folder. It is designed for human-approved, short-lived review of
low-sensitivity material. It is not an authenticated collaboration platform,
complete data-loss-prevention system, or safe transport for high-sensitivity
content.

## Data flow and trust boundaries

1. The CLI inventories the selected source folder without following excluded
   reparse points or symlinks.
2. Each permitted file is copied into a newly created temporary staging root.
   Source and staged hashes must match.
3. Secret scanning runs against the exact staged bytes.
4. The safe server exposes only the staging root on `127.0.0.1`.
5. After local verification and explicit approval, `cloudflared` publishes the
   loopback server through an unauthenticated Quick Tunnel.
6. On normal exit or a handled failure, child processes stop and the staging
   root is removed.

The source folder is never the HTTP document root. The generated public URL is
a bearer capability: anyone who obtains it can read the staged snapshot while
the process is running.

## Security guarantees

- Common VCS, dependency, environment, credential, key, and cloud-config paths
  are excluded by default.
- Reparse points and symlinks are not copied.
- Files larger than the configured copy limit are excluded.
- A content hash detects equal-length changes between inventory and staging.
- A high-signal secret match stops the workflow before the local server starts.
- The local server binds only to `127.0.0.1`; its CLI rejects non-loopback bind
  addresses.
- HTML, SVG, JavaScript, CSS, command files, and other recognized text formats
  are served as `text/plain`; unknown files use `application/octet-stream`.
- Responses use `no-store`, a restrictive Content Security Policy, `nosniff`,
  same-origin resource policy, and no-referrer policy.
- Public mode requires the exact word `SHARE` unless an approved caller
  explicitly uses `-Yes` or `--yes`.

## Known limitations

- Secret scanning covers only the configured text extensions and files of 2 MiB
  or less. The default copy limit is 25 MiB. Binary files, larger text files,
  organization-specific formats, and unknown credential patterns may not be
  scanned.
- A successful scan does not prove that the snapshot is free of private or
  regulated data. Review the folder and add project-specific exclusions.
- Inert remote rendering does not make a downloaded file safe to execute.
- Quick Tunnel URLs have no password or identity check. URL leakage defeats the
  transport's confidentiality.
- Cleanup is guaranteed for normal exit and handled failures. Force-killing the
  process, terminating the host, or an operating-system crash may leave a
  temporary directory until it is removed through an approved recovery process.
- `-Yes` and `--yes` bypass the interactive approval prompt. They do not grant
  authorization by themselves.

For high-sensitivity material, use an authenticated named tunnel with
Cloudflare Access or another organization-approved authenticated transport.
That infrastructure is outside this repository's scope.

## Machine-readable output

Windows `-Json` and macOS `--json` emit newline-delimited JSON (NDJSON) records
on stdout. Schema version 1 uses the same fields on both platforms:

| Field | Meaning |
| --- | --- |
| `schema_version` | Integer schema version; currently `1`. |
| `event` | `validated`, `public_ready`, `error`, or `cleanup`. |
| `mode` | `validate_only` or `public`. |
| `public_url` | Public review URL, or `null` before one exists. |
| `expires_at` | UTC ISO 8601 expiration time, or `null`. |
| `server_pid` | Local safe-server PID, or `null`. |
| `tunnel_pid` | `cloudflared` PID, or `null`. |
| `staging_root` | Explicit local staging path for lifecycle auditing. |
| `error` | Redacted error summary, or `null`. |

The `staging_root` field discloses a local path and appears only when the caller
explicitly requests JSON mode. It normally no longer exists by the `cleanup`
event. JSON public mode also requires `-Yes` or `--yes` so stdout cannot be
blocked by an interactive prompt.

## Residual-risk checklist

Before sharing, verify the selected folder, use `-AdditionalExclude` or
`--additional-exclude` for project-specific private paths, run validate-only,
obtain explicit approval, send the URL through an appropriate channel, and stop
the process as soon as review is complete.
