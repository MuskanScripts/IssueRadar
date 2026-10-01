import type { Availability } from "@/lib/demo";

/** "Free" is always the amber pill. Amber is reserved for this signal. */
export function FreePill({ availability }: { availability: Availability }) {
  if (availability === "free") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-amber px-2.5 py-0.5 text-sm font-semibold text-on-amber">
        <span aria-hidden="true" className="size-1.5 rounded-full bg-on-amber" />
        Free
      </span>
    );
  }
  if (availability === "likely_free") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-amber bg-amber-tint px-2.5 py-0.5 text-sm font-semibold text-amber-ink">
        Likely free
      </span>
    );
  }
  return null;
}
