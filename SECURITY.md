# Security Policy

[Traditional Chinese reference](SECURITY.zh-tw.md)

## Supported code

Until tagged releases exist, only the latest commit on `main` is supported.
Older commits and local modifications may not contain current safety fixes.

## Reporting a vulnerability

Use GitHub private vulnerability reporting for `pingqLIN/Quick-Tunnel` when it
is available. If that channel is unavailable, contact the repository owner
privately before publishing details. Do not open a public issue containing a
secret, a still-live tunnel URL, private source, credentials, or an exploit that
would expose another user's staged snapshot.

Include the affected platform and revision, the smallest redacted reproduction,
the expected safety boundary, and the observed behavior. Do not attach real
credentials or private project data.

## Security scope

Quick Tunnel Review Share is an unauthenticated, short-lived transport for a
filtered snapshot. It is not a private file-sharing service, complete DLP
system, or authenticated collaboration platform. See the
[threat model](docs/THREAT_MODEL.md) for guarantees, limitations, and safer
alternatives for sensitive material.
