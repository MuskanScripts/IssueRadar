# 0009. Fonts are bundled, not loaded from Google

- Status: accepted
- Date: 2026-10-01

## Context

The design uses Bricolage Grotesque, Instrument Sans and JetBrains Mono (all
SIL Open Font License). Loading them from Google Fonts sends every visitor's IP
address to a third party and fails offline.

## Decision

Use the `@fontsource-variable/*` npm packages so the fonts are bundled into the
build and served by FirstPR itself.

## Consequences

No third-party requests from the dashboard. A slightly larger build. The OFL
licence is compatible with MIT distribution; the licences ship inside the packages.
