import { layout } from "./Radar";
import type { Issue } from "@/lib/types";

function issue(n: number, tier: Issue["tier"], score: number, language: string): Issue {
  return { repo: "o/r", number: n, tier, difficulty_score: score, language, health: 50 } as Issue;
}

it("puts tiers in rings: beginner inside, pro outside", () => {
  const { dots } = layout([issue(1, "beginner", 10, "python"), issue(2, "pro", 90, "python")]);
  const radius = (d: (typeof dots)[number]) => Math.hypot(d.x - 320, d.y - 320);
  expect(radius(dots[0]!)).toBeLessThan(118);
  expect(radius(dots[1]!)).toBeGreaterThan(210);
});

it("groups languages into at most eight sectors", () => {
  const many = Array.from({ length: 12 }, (_, i) => issue(i, "beginner", 10, `lang${i}`));
  expect(layout(many).sectors).toHaveLength(8);
  expect(layout(many).sectors.at(-1)!.label).toBe("other");
});

it("keeps dots at least 8px across, bigger for healthier repos", () => {
  const { dots } = layout([{ ...issue(1, "beginner", 10, "go"), health: 0 }, { ...issue(2, "beginner", 10, "go"), health: 100 }]);
  expect(dots[0]!.r * 2).toBeGreaterThanOrEqual(8);
  expect(dots[1]!.r).toBeGreaterThan(dots[0]!.r);
});
