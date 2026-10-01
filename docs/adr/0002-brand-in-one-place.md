# 0002. Product name lives in one file

- Status: accepted
- Date: 2026-10-01

## Context

"FirstPR" is a working name and may change. If the name is spread across
imports, package names and UI strings, renaming becomes a large, risky change.

## Decision

- The code name is `issueradar` (the repository name). It is used for the
  Python import package and internal identifiers and does not change with the
  brand.
- Everything a user sees (product name, CLI command, tagline, demo label, env
  var prefix) is read from `src/issueradar/brand.json`. Python reads it through
  `issueradar.brand`; the web app imports the same file.
- The CLI command name must also appear in `pyproject.toml` (`[project.scripts]`),
  which cannot read JSON. A test fails if the two disagree.
- No document claims the name is available anywhere.

## Consequences

A rename is: edit `brand.json`, edit one line in `pyproject.toml`, run tests.
The PyPI distribution name is also in `pyproject.toml` and is checked by the
same test.
