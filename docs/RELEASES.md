# Release Policy

[Traditional Chinese reference](RELEASES.zh-tw.md)

Quick Tunnel Review Share has not published a tagged release. Until the first
release, `main` is the only supported line and may change without a stable API
guarantee.

## Versioning

The project uses Semantic Versioning for tagged releases. Its public interface
includes CLI flags, machine-readable event fields, installation paths,
supported platforms, and documented safety boundaries.

The intended first release is `v0.1.0`, but neither this document nor an
`Unreleased` changelog entry creates a release. A tag and GitHub Release require
an explicit publication decision after the exact commit passes CI and the
release checklist.

## Release checklist

1. Update `CHANGELOG.md` and its Traditional Chinese companion with the version
   and date.
2. Run the complete Windows and native macOS verification for the exact release
   candidate.
3. Confirm the GitHub Actions checks for that commit.
4. Review the source-only release scope for secrets, private URLs, local paths,
   research reports, and planning material.
5. Confirm compatibility or document every intentional breaking change.
6. Obtain explicit authorization before creating or pushing a tag or publishing
   a GitHub Release.
7. Verify the published tag resolves to the approved commit.

Release automation is intentionally deferred until the first release scope and
publication approval are established. This prevents an ordinary tag push from
silently becoming a public release.
