# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/).

## [Unreleased]

### Added (M1)

- Read-only GitHub client: REST `GET` only and GraphQL queries only, enforced by tests.
- API budgeter that tracks core, search and GraphQL budgets from response headers and stops at a safety margin.
- Retry rules from GitHub's docs: `retry-after`, at least a minute for secondary limits, exponential backoff, fixed retry count.
- ETag cache in the database; a second sync of an unchanged repo uses no budget (RESULTS.md).
- SQLite storage with Alembic migrations for every table in the brief.
- `firstpr watch add/remove/list`, `firstpr sync`, and `firstpr doctor --measure-etag`.
- Sync resumes after a quota hit, and one failing repo no longer stops the run.
- Fixture recorder script and recorded real responses; tests block the network.

### Changed (M1)

- PR references are split into closing (strong) and mentioned (weak); bot PR bodies are skipped, after real data showed heavy noise.
- Dependabot no longer proposes React major upgrades.

### Added (M0)

- M0 scaffold: Python package with `firstpr --version`, `doctor` and `demo`.
- Config schema with every GitHub limit and scoring weight, validated with friendly errors.
- Demo dataset, labelled "Demo data", shared by the CLI and the web app.
- Web shell (React, Vite, Tailwind CSS v4) with light and dark design tokens and contrast tests.
- CI (lint, type-check, tests, build, package build, secret scan) and Dependabot.
- PLAN.md, ADRs 0001 to 0011, GitHub API notes, contributor and security docs.
