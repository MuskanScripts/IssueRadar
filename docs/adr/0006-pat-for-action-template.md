# 0006. The Action template uses a personal access token

- Status: accepted
- Date: 2026-10-01

## Context

The built-in `GITHUB_TOKEN` is limited to 1,000 requests per hour per
repository, and its permissions are scoped to the workflow's repository. The
docs do not say whether it can read other repositories' public data.

## Decision

The fork-and-run template reads a fine-grained personal access token from a
repository secret. The recommended token has resource owner = the user,
repository access "Public repositories (read-only)", and no extra permissions.
Fine-grained tokens always include read-only access to public repositories.

## Consequences

Users must create a token (documented step by step). We will still measure what
`GITHUB_TOKEN` can do in M6 and record it.
