import type { Tier } from "@/lib/types";

const FILLED: Record<Tier, number> = { beginner: 1, intermediate: 2, pro: 3 };
const LABEL: Record<Tier, string> = { beginner: "Beginner", intermediate: "Intermediate", pro: "Pro" };

/** Level is always three dots: one filled = Beginner, two = Intermediate, three = Pro. */
export function LevelDots({ tier }: { tier: Tier }) {
  const filled = FILLED[tier];
  return (
    <span className="inline-flex items-center gap-1" role="img" aria-label={`Level: ${LABEL[tier]}`}>
      {[1, 2, 3].map((n) => (
        <span
          key={n}
          className={n <= filled ? "size-2 rounded-full bg-ink" : "size-2 rounded-full border-[1.5px] border-ink-muted"}
        />
      ))}
    </span>
  );
}
