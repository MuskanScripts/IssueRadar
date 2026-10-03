# Design tokens

Source of truth: [`web/src/styles/tokens.css`](../web/src/styles/tokens.css).
Components use the role names below (as Tailwind classes such as `bg-ground`
or `text-ink-muted`), never raw hex values.

A test (`web/src/styles/tokens.test.ts`) checks WCAG AA contrast for every
text and UI pairing in both themes, and that the light theme still matches the
landing page.

## Colour roles

| Role | Light | Dark | Use |
| --- | --- | --- | --- |
| `ground` | `#F1F4F5` | `#0A121C` | Page background |
| `surface` | `#FBFCFC` | `#101A26` | Cards, secondary panels |
| `surface-raised` | `#FFFFFF` | `#152232` | Lists, drawers, menus |
| `ink` | `#0E1B2C` | `#EEF2F5` | Main text |
| `ink-secondary` | `#33465A` | `#C3CFDA` | Body text, descriptions |
| `ink-muted` | `#4A5B6B` | `#9AAABA` | Metadata (still AA on every surface) |
| `rule` | `#CBD5DB` | `#33465A` | Borders |
| `rule-soft` | `#E1E7EB` | `#1F2E3F` | Dividers inside a component |
| `action` | `#2455F4` | `#8FA8FF` | Links, primary buttons |
| `action-hover` | `#1B43CC` | `#B3C4FF` | Hover state |
| `action-tint` | `#E4EAFF` | `#1A2850` | Selected rows, neutral status chips |
| `on-action` | `#FFFFFF` | `#0A121C` | Text on `action` |
| `amber` | `#F2B01E` | `#F2B01E` | The "Free" pill only |
| `amber-tint` | `#FCEFC7` | `#3A2C06` | "Likely free" background |
| `amber-ink` | `#5C4200` | `#F8D47A` | Text on `amber-tint` |
| `on-amber` | `#0E1B2C` | `#0E1B2C` | Text on `amber` |
| `focus` | `#0E1B2C` | `#EEF2F5` | Focus outline (3px) |
| `chart-1` | `#2455F4` | `#5B7FFF` | The one chart series colour; both pass the dataviz palette checks against their surface |

The dark theme follows the system setting unless the user picks Light or Dark.

## Type

- **Bricolage Grotesque** for display (headings, the wordmark).
- **Instrument Sans** for body text.
- **JetBrains Mono** for data and code (repo names, numbers, the demo label).

Fonts are bundled from `@fontsource-variable` packages (ADR 0009).

## Rules

- Sentence case everywhere. Acronyms keep their capitals ("CI failing").
- Level is always three dots: one filled = Beginner, two = Intermediate, three = Pro. Each set has an accessible name ("Level: Beginner").
- "Free" is always the amber pill. Amber is the only saturated signal.
- Avoid gradient washes, identical card grids with the same shadow, all-caps eyebrow labels, emoji, left-border accent cards, and the fonts Inter, Roboto and Arial.
- Motion: one sweep on the Radar's first load (M5), nothing else, and none when `prefers-reduced-motion` is set.
