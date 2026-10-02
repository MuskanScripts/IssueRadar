import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const PAGES = [
  ["/", "Radar"],
  ["/repos", "Repos"],
  ["/prs", "My pull requests"],
  ["/profile", "Profile"],
  ["/digest", "Digest"],
  ["/insights", "Insights"],
  ["/settings", "Settings"],
] as const;

async function noSeriousViolations(page: Page, theme: "light" | "dark") {
  await page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), theme);
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(
    serious.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`),
    `${theme} theme`,
  ).toEqual([]);
}

for (const [path, heading] of PAGES) {
  test(`${heading} renders in demo mode with no serious accessibility problems`, async ({ page }) => {
    await page.goto(`${path}?demo=1`);
    await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
    await expect(page.getByText("Demo data").first()).toBeVisible();
    await page.waitForTimeout(400); // let the first-load sweep finish
    await noSeriousViolations(page, "light");
    await noSeriousViolations(page, "dark");
  });
}

test("the main flow works by keyboard alone", async ({ page }, info) => {
  test.skip(info.project.name === "phone", "keyboard flow is a desktop check");
  await page.goto("/?demo=1");
  const list = page.getByRole("list", { name: /issues, best match first/i });
  await expect(list.getByRole("listitem").first()).toBeVisible();

  // Search with "/", then clear it again.
  await page.keyboard.press("/");
  await expect(page.getByPlaceholder(/search titles/i)).toBeFocused();
  await page.keyboard.type("test");
  await expect(list.getByRole("listitem").first()).toContainText(/test/i);
  await page.keyboard.press("Control+A");
  await page.keyboard.press("Backspace");
  await page.keyboard.press("Tab");

  // j moves, o opens the drawer, Escape closes it and focus comes back.
  await page.keyboard.press("j");
  await page.keyboard.press("o");
  const drawer = page.getByRole("dialog");
  await expect(drawer.getByText("Why it is free (or not)")).toBeVisible();
  await expect(drawer.getByText("Before you start")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(drawer).toBeHidden();

  // x dismisses the selected issue.
  const before = await list.getByRole("listitem").count();
  await page.keyboard.press("j");
  await page.keyboard.press("x");
  await expect(list.getByRole("listitem")).toHaveCount(before - 1);

  // Ctrl+K jumps to another page.
  await page.keyboard.press("Control+k");
  await page.keyboard.type("my prs");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { level: 1, name: "My pull requests" })).toBeVisible();

  // Tab reaches the main navigation.
  await page.keyboard.press("Tab");
  await expect(page.locator(":focus")).toBeVisible();
});

test("radar shows dots and opens an issue on click", async ({ page }) => {
  await page.goto("/?demo=1");
  const dots = page.getByTestId("radar-dot");
  await expect(dots.first()).toBeAttached();
  expect(await dots.count()).toBeGreaterThan(5);
  await dots.first().dispatchEvent("click");
  await expect(page.getByRole("dialog")).toBeVisible();
});

test("no horizontal scroll at phone width", async ({ page }, info) => {
  test.skip(info.project.name !== "phone", "phone only");
  for (const [path] of PAGES) {
    await page.goto(`${path}?demo=1`);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, path).toBeLessThanOrEqual(1);
  }
});
