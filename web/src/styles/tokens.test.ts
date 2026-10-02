import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// Vitest runs from web/, so this path is stable in CI and locally.
const css = readFileSync(resolve(process.cwd(), "src/styles/tokens.css"), "utf8");

/** Extract the custom properties declared in the first block matching `selector`. */
function block(selector: string): Record<string, string> {
  const start = css.indexOf(selector);
  if (start < 0) throw new Error(`no block for ${selector}`);
  const open = css.indexOf("{", start);
  const close = css.indexOf("}", open);
  const tokens: Record<string, string> = {};
  for (const m of css.slice(open + 1, close).matchAll(/--([\w-]+):\s*(#[0-9a-f]{6})/gi)) {
    tokens[m[1]!] = m[2]!;
  }
  return tokens;
}

function luminance(hex: string): number {
  const channels = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const [r, g, b] = channels.map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi! + 0.05) / (lo! + 0.05);
}

// [foreground, background, minimum ratio]. 4.5 for text, 3 for UI parts.
const PAIRS: [string, string, number][] = [
  ["ink", "ground", 4.5],
  ["ink", "surface-raised", 4.5],
  ["ink-secondary", "ground", 4.5],
  ["ink-secondary", "surface", 4.5],
  ["ink-muted", "ground", 4.5],
  ["ink-muted", "surface-raised", 4.5],
  ["action", "ground", 4.5],
  ["action", "surface-raised", 4.5],
  ["on-action", "action", 4.5],
  ["on-action", "action-hover", 4.5],
  ["ink", "action-tint", 4.5],
  ["on-amber", "amber", 4.5],
  ["amber-ink", "amber-tint", 4.5],
  ["focus", "ground", 3],
  ["focus", "surface-raised", 3],
];

const themes = {
  light: block(":root {"),
  dark: block(':root[data-theme="dark"]'),
};

describe.each(Object.entries(themes))("%s theme", (_name, tokens) => {
  it.each(PAIRS)("%s on %s meets %s:1", (fg, bg, min) => {
    expect(tokens[fg], `missing --${fg}`).toBeDefined();
    expect(tokens[bg], `missing --${bg}`).toBeDefined();
    expect(contrast(tokens[fg]!, tokens[bg]!)).toBeGreaterThanOrEqual(min);
  });
});

it("system dark and forced dark use the same values", () => {
  expect(block(':root:not([data-theme="light"])')).toEqual(themes.dark);
});

it("light theme matches the landing page palette", () => {
  expect(themes.light).toMatchObject({
    ground: "#f1f4f5",
    ink: "#0e1b2c",
    action: "#2455f4",
    "action-hover": "#1b43cc",
    amber: "#f2b01e",
    "amber-ink": "#5c4200",
  });
});
