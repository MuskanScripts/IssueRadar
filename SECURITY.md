# Security policy

## Reporting a vulnerability

Please **do not open a public issue** for security problems. Use GitHub's
private vulnerability reporting on this repository (the **Security** tab,
**Report a vulnerability**). You should get a first reply within 7 days.

## What FirstPR does to stay safe

- **Read-only toward GitHub.** The GitHub client refuses every non-GET REST request and every GraphQL mutation, and tests enforce it (from M1).
- **Least-privileged tokens.** We recommend a fine-grained token with read-only access to public repositories and no extra permissions. See [docs/human-tasks.md](docs/human-tasks.md).
- **No secrets in the repository.** Tokens come from environment variables or GitHub Actions secrets. `.env` is git-ignored, and CI runs a secret scan on every push.
- **No telemetry.** FirstPR sends nothing anywhere except requests to the GitHub API and the delivery channels you configure.

## Supported versions

Only the latest release receives fixes until 1.0.
