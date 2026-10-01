# Contributing

Thank you for helping. FirstPR exists to make people better open-source
contributors, so we try to be a good project to contribute to.

## Before you start

1. Look for an issue labelled with a level (Beginner, Intermediate or Pro). If there isn't one for your idea, open an issue first so we can agree on the approach.
2. Comment on the issue to say you are working on it.
3. Keep one issue per pull request, and keep the diff small.

## Set up

Follow the quick start in the [README](README.md). Everything is given as
PowerShell commands, and it works the same on macOS and Linux shells.

## Rules of the codebase

- **Read-only toward GitHub.** Never add code that writes to GitHub (ADR 0004).
- **Tests never touch the network.** Use recorded fixtures of real public API responses.
- **No made-up data.** Anything shown as real must come from the API. Sample data says "Demo data".
- **Limits and weights go in config**, not in code (ADR 0005).
- **Big decisions get an ADR** in `docs/adr` (copy `0000-template.md`).
- **Sentence case** in all user-facing text.

## Before you open a pull request

Run the checks listed in the README for the part you changed (Python, web or
both). Add or update tests for behaviour you change, and update docs if a user
would notice. Fill in the pull request template.

## Code of conduct

This project follows the [Code of Conduct](CODE_OF_CONDUCT.md).
