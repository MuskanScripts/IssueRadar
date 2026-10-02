import { FreePill } from "@/components/FreePill";
import { LevelDots } from "@/components/LevelDots";
import { sentence, type DemoIssue, type DemoRepo } from "@/lib/demo";

interface Props {
  issues: DemoIssue[];
  repos: DemoRepo[];
}

export function IssueList({ issues, repos }: Props) {
  const health = new Map(repos.map((r) => [r.full_name, r.health.score]));
  return (
    <ol aria-label="Free issues, best match first" className="divide-y divide-rule-soft rounded-xl border border-rule bg-surface-raised">
      {issues.map((issue) => (
        <li
          key={`${issue.repo}#${issue.number}`}
          className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 px-4 py-4 sm:grid-cols-[auto_1fr_auto] sm:px-5"
        >
          <span className="pt-2">
            <LevelDots tier={issue.tier} />
          </span>
          <div className="min-w-0">
            <p className="font-semibold text-ink">{issue.title}</p>
            <p className="font-mono text-[13px] text-ink-muted">
              {issue.repo}#{issue.number}
              <span aria-hidden="true"> · </span>
              <span className="sr-only">, </span>
              {issue.language}
              <span aria-hidden="true"> · </span>
              <span className="sr-only">, </span>
              {sentence(issue.time_bucket)}
              <span aria-hidden="true"> · </span>
              <span className="sr-only">, </span>
              health {health.get(issue.repo)}
            </p>
            <p className="mt-1 text-[15px] text-ink-secondary">{issue.why_here}</p>
          </div>
          <span className="col-start-2 sm:col-start-3 sm:pt-0.5">
            <FreePill availability={issue.availability} />
          </span>
        </li>
      ))}
    </ol>
  );
}
