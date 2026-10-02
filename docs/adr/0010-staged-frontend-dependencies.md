# 0010. Frontend dependencies arrive with the milestone that uses them

- Status: accepted
- Date: 2026-10-01

## Context

The decided web stack is large (shadcn/ui, TanStack Query and Table, React
Router, cmdk, Recharts, Framer Motion, Playwright, axe). Installing it all in
M0 adds unused code, Dependabot noise and lines the owner cannot yet explain.

## Decision

M0 installs only React, Vite, TypeScript, Tailwind CSS v4, the fonts and
Vitest with Testing Library. The rest of the stack in brief section 3 is still
decided; each package is added in the milestone that first uses it (mostly M5).

## Consequences

Smaller M0 diff. The stack itself is unchanged, so this is not a deviation that
needs its own ADR per package.
