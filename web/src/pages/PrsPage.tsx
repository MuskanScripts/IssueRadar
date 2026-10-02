import { Copy } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, Loading, Pill } from "@/components/ui/states";
import { usePulls } from "@/lib/data";
import type { Pull } from "@/lib/types";
import { relativeDays } from "@/lib/utils";

const COLUMNS: { status: string[]; title: string }[] = [
  { status: ["changes_requested", "ci_failing", "merge_conflict"], title: "Needs you" },
  { status: ["stale"], title: "Gone quiet" },
  { status: ["waiting_for_review", "approved"], title: "Waiting on others" },
  { status: ["merged", "closed_unmerged"], title: "Done" },
];

function PullCard({ pull }: { pull: Pull }) {
  const [copied, setCopied] = useState(false);
  return (
    <li className="rounded-xl border border-rule bg-surface-raised p-4">
      <p className="font-semibold">
        {pull.url ? <a href={pull.url} target="_blank" rel="noreferrer">{pull.title}</a> : pull.title}
      </p>
      <p className="font-mono text-[13px] text-ink-muted">
        {pull.repo}#{pull.number}, opened {relativeDays(pull.opened_at)}
      </p>
      <p className="mt-2">
        <Pill>{pull.status_label}</Pill>
      </p>
      <p className="mt-2 text-[15px] text-ink-secondary">{pull.needs_you}</p>
      {pull.nudge ? (
        <div className="mt-3 rounded-lg bg-surface p-3">
          <p className="text-sm font-semibold">Nudge draft</p>
          <p className="mt-1 text-[15px] text-ink-secondary">{pull.nudge}</p>
          <Button
            size="sm"
            className="mt-2"
            onClick={() => {
              void navigator.clipboard?.writeText(pull.nudge ?? "");
              setCopied(true);
            }}
          >
            <Copy className="size-4" aria-hidden="true" /> {copied ? "Copied" : "Copy"}
          </Button>
          <p className="mt-2 text-[13px] text-ink-muted">You decide whether to send it. Nothing is posted for you.</p>
        </div>
      ) : null}
      {pull.timeline.length ? (
        <details className="mt-3 text-sm">
          <summary className="cursor-pointer text-ink-secondary">Timeline ({pull.timeline.length})</summary>
          <ol className="mt-2 space-y-1">
            {pull.timeline.map((event, index) => (
              <li key={index} className="flex gap-3">
                <span className="font-mono text-[12px] text-ink-muted">{event.at.slice(0, 10)}</span>
                <span>{event.text}</span>
              </li>
            ))}
          </ol>
        </details>
      ) : null}
    </li>
  );
}

export function PrsPage() {
  const pulls = usePulls();
  return (
    <div className="space-y-5">
      <h1 className="font-display text-4xl font-extrabold tracking-[-0.02em]">My pull requests</h1>
      {pulls.isPending ? (
        <Loading label="Loading pull requests" />
      ) : pulls.isError ? (
        <ErrorState error={pulls.error} onRetry={() => pulls.refetch()} />
      ) : pulls.data.length === 0 ? (
        <EmptyState title="No pull requests tracked yet">
          Run <code className="font-mono">firstpr prs</code> to find the pull requests you opened.
        </EmptyState>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {COLUMNS.map((column) => {
            const items = pulls.data.filter((p) => column.status.includes(p.status));
            return (
              <section key={column.title} aria-labelledby={`col-${column.title}`}>
                <h2 id={`col-${column.title}`} className="mb-3 font-display text-lg font-bold">
                  {column.title} <span className="font-mono text-sm text-ink-muted">{items.length}</span>
                </h2>
                {items.length ? (
                  <ul className="space-y-3">{items.map((p) => <PullCard key={`${p.repo}#${p.number}`} pull={p} />)}</ul>
                ) : (
                  <p className="text-sm text-ink-muted">Nothing here.</p>
                )}
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}
