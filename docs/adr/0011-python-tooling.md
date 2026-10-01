# 0011. Plain venv and pip, hatchling backend

- Status: accepted
- Date: 2026-10-01

## Context

The owner works on Windows 11 with PowerShell and Python 3.13. Setup should be a
few commands with tools that ship with Python.

## Decision

- Development uses `py -3.13 -m venv .venv` and `pip install -e ".[dev]"`.
  No extra tool is required (uv works too, but is not needed).
- Build backend: `hatchling`. Package data (`brand.json`, config defaults,
  demo fixtures) ships inside the wheel.
- Supported Python: 3.11 and newer. CI tests 3.11 and 3.13.
- Lint and format: ruff. Types: mypy in strict mode for `src/`.

## Consequences

No lock file for Python in M0; dependency ranges are pinned loosely in
`pyproject.toml`. Revisit when packaging for release (M6).
