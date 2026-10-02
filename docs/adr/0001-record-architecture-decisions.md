# 0001. Record architecture decisions

- Status: accepted
- Date: 2026-10-01

## Context

The project owner must be able to explain every line that ships, including why
it was built that way. Decisions made in chat or commit messages get lost.

## Decision

Every significant decision gets a short ADR in `docs/adr`, numbered in order,
using `0000-template.md`. "Significant" means: it changes the stack, a public
interface, data that is stored, how GitHub is called, or something a user will
notice. A changed decision gets a new ADR that supersedes the old one; old ADRs
are not rewritten.

## Consequences

A small writing cost per decision. `PLAN.md` keeps a one-line summary table.
