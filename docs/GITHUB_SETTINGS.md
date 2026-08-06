# GitHub Repository Settings

[Traditional Chinese reference](GITHUB_SETTINGS.zh-tw.md)

Files in this repository provide review and test definitions, but they do not
enforce GitHub-hosted policy by themselves. A repository administrator must
configure the following settings separately.

## Recommended `main` ruleset

- Require a pull request before merging.
- Require at least one approval and Code Owner review.
- Dismiss stale approvals after new reviewable commits.
- Require conversation resolution.
- Block force pushes and branch deletion.
- Require the `windows`, `macos`, `python-3-14`, and `dependency-review` checks
  after each check has run successfully at least once on the repository.

Do not select a required-check name until GitHub has recorded the corresponding
check. A local test result is not an enforcement setting.

## Security settings

- Keep the dependency graph enabled.
- Confirm secret scanning for the public repository and enable repository push
  protection when the account plan exposes that control.
- Enable CodeQL default setup for Python. Default setup is preferred over a
  repository workflow here because the project does not need a custom build.
- Require GitHub Actions to use full-length commit SHAs where the repository
  setting is available.

These are public-repository control-plane mutations. They require separate
administrator authorization and must be verified on GitHub; committing this
document does not enable them.
