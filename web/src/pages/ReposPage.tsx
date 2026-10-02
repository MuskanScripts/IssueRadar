import { EmptyState, ErrorState, Loading } from "@/components/ui/states";
import { useRepos } from "@/lib/data";
import { sentence } from "@/lib/demo";
import { relativeDays } from "@/lib/utils";

export function ReposPage() {
  const repos = useRepos();
  return (
    <div className="space-y-5">
      <h1 className="font-display text-4xl font-extrabold tracking-[-0.02em]">Repos</h1>
      <p className="max-w-2xl text-ink-secondary">
        Your watchlist. Health says how likely a maintainer is to review your pull request; the breakdown says why.
      </p>
      {repos.isPending ? (
        <Loading label="Loading repos" />
      ) : repos.isError ? (
        <ErrorState error={repos.error} onRetry={() => repos.refetch()} />
      ) : repos.data.length === 0 ? (
        <EmptyState title="You're not watching any repos yet">
          Add one with <code className="font-mono">firstpr watch add owner/repo</code>, or a starter pack with{" "}
          <code className="font-mono">firstpr pack add ai-agents-and-mcp</code>.
        </EmptyState>
      ) : (
        <ul className="grid gap-4 lg:grid-cols-2">
          {repos.data.map((repo) => (
            <li key={repo.full_name} className="rounded-xl border border-rule bg-surface-raised p-5">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <h2 className="truncate font-mono text-base font-semibold">{repo.full_name}</h2>
                  <p className="mt-1 text-[15px] text-ink-secondary">{repo.description}</p>
                </div>
                <div className="text-right">
                  <p className="font-display text-3xl font-extrabold">{repo.health ?? "n/a"}</p>
                  <p className="text-sm text-ink-muted">health</p>
                </div>
              </div>
              <p className="mt-3 font-mono text-[13px] text-ink-muted">
                {repo.language ?? "unknown"}, {repo.stars.toLocaleString()} stars, {repo.free_issues} free of{" "}
                {repo.open_issues} open, synced {relativeDays(repo.last_synced_at)}
              </p>
              {Object.keys(repo.health_parts).length ? (
                <dl className="mt-4 space-y-2">
                  {Object.entries(repo.health_parts).map(([part, value]) => (
                    <div key={part} className="grid grid-cols-[10rem_1fr_3rem] items-center gap-3 text-sm">
                      <dt className="text-ink-secondary">{sentence(part)}</dt>
                      <dd className="h-2 rounded-full bg-rule-soft" aria-hidden="true">
                        <div className="h-2 rounded-full bg-[var(--chart-1)]" style={{ width: `${(value ?? 0.5) * 100}%` }} />
                      </dd>
                      <dd className="text-right font-mono">{value === null ? "n/a" : Math.round(value * 100)}</dd>
                    </div>
                  ))}
                </dl>
              ) : null}
              <ul className="mt-3 space-y-1 text-sm text-ink-secondary">
                {repo.health_reasons.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
              {repo.sync_error ? <p className="mt-2 text-sm text-ink">Last sync failed: {repo.sync_error}</p> : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
