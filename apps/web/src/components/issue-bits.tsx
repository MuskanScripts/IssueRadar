import Link from "next/link";
import { issuePath, logEvent, type Issue, type Level } from "@/lib/api";

const DOTS: Record<Level, number> = { beginner: 1, intermediate: 2, pro: 3 };
const LEVEL_LABEL: Record<Level, string> = {
  beginner: "Beginner",
  intermediate: "Intermediate",
  pro: "Pro",
};

/** Level is always three dots, so it never depends on colour alone. */
export function LevelDots({ level }: { level: Level }) {
  const filled = DOTS[level];
  return (
    <span className="inline-flex items-center gap-1.5 text-sm" title={`${LEVEL_LABEL[level]} level`}>
      <span aria-hidden="true" className="tracking-tight">
        {"●".repeat(filled)}
        <span className="text-line">{"●".repeat(3 - filled)}</span>
      </span>
      <span>{LEVEL_LABEL[level]}</span>
    </span>
  );
}

export function StateBadge({ issue }: { issue: Pick<Issue, "availability" | "availability_label"> }) {
  const open = issue.availability === "free" || issue.availability === "likely_free";
  return (
    <span
      className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${
        open ? "border-good/40 text-good" : "border-warn/40 text-warn"
      }`}
    >
      {issue.availability_label}
    </span>
  );
}

export function FitBadge({ fit }: { fit: number | null }) {
  if (fit === null) return null;
  return (
    <span className="rounded-full bg-accent/10 px-2 py-0.5 text-xs font-semibold text-accent">
      {fit}% fit
    </span>
  );
}

export function IssueMeta({ issue }: { issue: Issue }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-ink-2">
      <LevelDots level={issue.tier} />
      <span>{issue.time_label}</span>
      {issue.language ? <span>{issue.language}</span> : null}
      <span>
        {issue.comments} comment{issue.comments === 1 ? "" : "s"}
      </span>
      {issue.health !== null ? <span>Repo health {issue.health}</span> : null}
    </div>
  );
}

/** One row in a list of issues: Explore, and anywhere else issues are listed. */
export function IssueRow({
  issue,
  surface,
  badge,
}: {
  issue: Issue;
  surface: "daily" | "explore";
  badge?: React.ReactNode;
}) {
  return (
    <li className="flex flex-col gap-2 rounded-lg border border-line bg-surface p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-sm text-ink-2">
          {issue.repo} #{issue.number}
        </span>
        <StateBadge issue={issue} />
        <FitBadge fit={issue.fit} />
        {issue.held_by_you ? (
          <span className="rounded-full border border-accent/40 px-2 py-0.5 text-xs font-semibold text-accent">
            Your pick
          </span>
        ) : null}
        {badge}
      </div>
      <Link
        href={issuePath(issue)}
        onClick={() => logEvent(issue, surface, "opened")}
        className="text-lg font-semibold hover:underline"
      >
        {issue.title}
      </Link>
      <IssueMeta issue={issue} />
      {issue.why.length ? <p className="text-sm text-ink-2">{issue.why.slice(0, 3).join(" · ")}</p> : null}
    </li>
  );
}

export function timeAgo(iso: string | null) {
  if (!iso) return "never";
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  return hours < 48 ? `${hours} h ago` : `${Math.round(hours / 24)} days ago`;
}
