## Summary

Describe what changed and why.

## Change type

- [ ] Feature
- [ ] Fix
- [ ] Documentation
- [ ] Refactor
- [ ] Test
- [ ] Security
- [ ] Maintenance

## Safety and compatibility

- [ ] The source folder is never served directly.
- [ ] Secret, exclusion, staging, and cleanup boundaries are unchanged or tested.
- [ ] Public sharing still requires explicit approval.
- [ ] CLI, installation, platform, and output-schema compatibility is documented.
- [ ] No real secret, private URL, customer data, or live tunnel URL is included.

## Verification

List the exact commands and results. Include Windows and macOS evidence when
the change affects both implementations.

- [ ] Relevant local tests pass.
- [ ] English and Traditional Chinese operator documentation remain aligned.
- [ ] `CHANGELOG.md` is updated for a user-visible change.
- [ ] The threat model is updated for a security-boundary change.

## Risk and rollback

Describe the highest relevant risk and how the change can be rolled back.

[Traditional Chinese reference](pull_request_template.zh-tw.md)
