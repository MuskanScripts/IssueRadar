import { TIER_DOTS, sentence, type Tier } from "@/lib/demo";

/** Level is always three dots: one filled = Beginner, two = Intermediate, three = Pro. */
export function LevelDots({ tier }: { tier: Tier }) {
  const filled = TIER_DOTS[tier];
  return (
    <span className="inline-flex items-center gap-1" role="img" aria-label={`Level: ${sentence(tier)}`}>
      {[1, 2, 3].map((n) => (
        <span
          key={n}
          className={
            n <= filled
              ? "size-2 rounded-full bg-ink"
              : "size-2 rounded-full border-[1.5px] border-ink-muted"
          }
        />
      ))}
    </span>
  );
}
