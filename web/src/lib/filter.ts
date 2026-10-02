import type { Filters, Issue } from "./types";

/** Client-side filtering: instant feedback while typing or clicking chips. */
export function applyFilters(issues: Issue[], f: Filters): Issue[] {
  const q = f.q.trim().toLowerCase();
  return issues.filter(
    (i) =>
      (!f.level.length || f.level.includes(i.tier)) &&
      (!f.language.length || f.language.includes((i.language ?? "").toLowerCase())) &&
      (!f.type.length || f.type.includes(i.issue_type)) &&
      (!f.time.length || f.time.includes(i.time_bucket)) &&
      (f.min_health === null || (i.health ?? 0) >= f.min_health) &&
      (f.max_comments === null || i.comments <= f.max_comments) &&
      (!f.no_discussion || !i.discussion_first) &&
      (!q || `${i.title} ${i.repo} ${i.labels.join(" ")}`.toLowerCase().includes(q)),
  );
}

export function languagesOf(issues: Issue[]): string[] {
  return [...new Set(issues.map((i) => (i.language ?? "").toLowerCase()).filter(Boolean))].sort();
}

export function activeCount(f: Filters): number {
  return (
    f.level.length +
    f.language.length +
    f.type.length +
    f.time.length +
    (f.min_health !== null ? 1 : 0) +
    (f.max_comments !== null ? 1 : 0) +
    (f.no_discussion ? 1 : 0) +
    (f.q ? 1 : 0)
  );
}
