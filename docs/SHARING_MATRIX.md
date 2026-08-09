# Sharing and Filtering Matrix

Quick Tunnel Review Share is a filtered snapshot tool, not a private file-sharing
service or complete data-loss-prevention system. Use this matrix before choosing
whether and how to share a folder.

[Traditional Chinese reference](SHARING_MATRIX.zh-tw.md)

| Sharing situation | What the default filter does | Required operator check | Recommended mode | Exposure and residual risk |
| --- | --- | --- | --- | --- |
| Routine code review | Excludes common VCS, dependency, environment, credential, key, and cloud-config paths; blocks configured high-signal secret patterns in scanned text files | Inspect the selected folder and add project-specific rules with `-AdditionalExclude` | Run `-ValidateOnly` first, then use interactive `SHARE` approval | The live URL is unauthenticated; anyone who obtains it can read the filtered snapshot |
| Private, regulated, credential-bearing, or otherwise high-sensitivity material | Provides useful defaults, but does not guarantee that every private datum or credential is detected | Do not rely on the default filter as DLP; remove private material or use an approved private-sharing channel | Do not open public mode; use `-ValidateOnly` only when a local snapshot is still appropriate | Public mode is not suitable; inert browser rendering does not make downloaded files safe to execute |
| Automated or pre-approved workflow | Applies the same inventory, staging, size, and secret-scan gates | Predefine exclusions, record the approval boundary, and handle `staging_root` as local-path data when using JSON | Use `-Yes` only inside the approved workflow; use `-Json` for machine-readable lifecycle events | `-Yes` bypasses the interactive prompt and still creates an unauthenticated public endpoint |
| Large, binary, or unknown-format files | Files above the copy limit are skipped; secret scanning covers only configured text extensions at or below 2 MiB | Review the validation result and assume unscanned content may still be copied when within the separate copy limit | Validate locally and inspect the snapshot before any public share | The filter cannot guarantee detection of secrets in unscanned formats or oversized text files |

## Decision rules

- `-ValidateOnly` builds and checks the local filtered snapshot without opening a
  public tunnel.
- `-AdditionalExclude` is the control for repository-specific private paths; it
  should be applied before public sharing, not after a URL is created.
- The default copy limit is 25 MiB per file, while the configured secret scan
  covers only text files at or below 2 MiB.
- Public sharing requires the exact interactive word `SHARE`, unless an approved
  caller explicitly uses `-Yes` or `--yes`.
- The default filter is a safety baseline. It is not proof that a folder is safe
  to publish.

For the implementation details and residual-risk checklist, see the
[threat model](THREAT_MODEL.md).
