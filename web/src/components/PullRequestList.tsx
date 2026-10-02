import { sentence, type DemoPullRequest } from "@/lib/demo";

export function PullRequestList({ pulls }: { pulls: DemoPullRequest[] }) {
  return (
    <ul aria-label="Pull requests you opened" className="grid gap-3 sm:grid-cols-2">
      {pulls.map((pr) => (
        <li key={`${pr.repo}#${pr.number}`} className="rounded-xl border border-rule bg-surface p-4">
          <p className="font-semibold text-ink">{pr.title}</p>
          <p className="font-mono text-[13px] text-ink-muted">
            {pr.repo}#{pr.number}
          </p>
          <p className="mt-2 text-sm">
            <span className="rounded-md bg-action-tint px-2 py-0.5 font-medium text-ink">
              {sentence(pr.status)}
            </span>
          </p>
          <p className="mt-2 text-[15px] text-ink-secondary">{pr.needs_you}</p>
        </li>
      ))}
    </ul>
  );
}
