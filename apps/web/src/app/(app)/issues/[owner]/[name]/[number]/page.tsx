"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ComingSoon } from "@/components/coming-soon";
import { FitBadge, IssueMeta, StateBadge, timeAgo } from "@/components/issue-bits";
import { timeLeft, useNow } from "@/components/use-now";
import { getJson, logEvent, type IssueDetail } from "@/lib/api";

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-line bg-surface p-5">
      <h2 className="mb-2 font-semibold">{title}</h2>
      {children}
    </section>
  );
}

function Lines({ items }: { items: string[] }) {
  if (!items.length) return <p className="text-sm text-ink-2">Nothing to add.</p>;
  return (
    <ul className="list-disc space-y-1 pl-5 text-sm text-ink-2">
      {items.map((line) => (
        <li key={line}>{line}</li>
      ))}
    </ul>
  );
}

export default function IssuePage() {
  const { owner, name, number } = useParams<{ owner: string; name: string; number: string }>();
  const now = useNow();
  const { data: issue, error } = useQuery({
    queryKey: ["issue", owner, name, number],
    queryFn: () => getJson<IssueDetail>(`/api/v1/issues/${owner}/${name}/${number}`, "this issue"),
  });

  if (error) {
    return (
      <main className="flex flex-col gap-3">
        <p className="text-warn">{error.message}</p>
        <Link href="/explore" className="font-semibold text-accent underline">
          Back to Explore
        </Link>
      </main>
    );
  }
  if (!issue) return <p className="text-ink-2">Loading</p>;
  const open = issue.availability === "free" || issue.availability === "likely_free";

  return (
    <main className="flex flex-col gap-5">
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-sm text-ink-2">
            {issue.repo} #{issue.number}
          </span>
          <StateBadge issue={issue} />
          <FitBadge fit={issue.fit} />
          {issue.held_until ? (
            <span className="rounded-full border border-accent/40 px-2 py-0.5 text-xs font-semibold text-accent">
              Your pick, held for {timeLeft(issue.held_until, now)}
            </span>
          ) : null}
        </div>
        <h1 className="text-3xl font-bold">{issue.title}</h1>
        <IssueMeta issue={issue} />
        <p className="text-xs text-ink-2">
          Checked {timeAgo(issue.live?.checked_at ?? issue.refreshed_at)}
          {issue.live ? " on GitHub" : ""}.
        </p>
      </div>

      {issue.live?.note ? (
        <p role="alert" className="rounded-md border border-warn/40 border-l-4 border-l-warn bg-surface p-3 text-sm">
          {issue.live.note}
        </p>
      ) : null}

      <div className="flex flex-wrap gap-3">
        {issue.url ? (
          <a
            href={issue.url}
            target="_blank"
            rel="noreferrer"
            onClick={() => logEvent(issue, "issue", "github")}
            className="rounded-md bg-accent px-4 py-2 font-semibold text-accent-ink hover:opacity-90"
          >
            Open on GitHub
          </a>
        ) : null}
        <Link href="/explore" className="rounded-md border border-line px-4 py-2 font-semibold">
          Back to Explore
        </Link>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Panel title={open ? "Why we think it is free" : "What our last sync saw"}>
          <Lines items={issue.availability_reasons} />
        </Panel>
        <Panel title="Why it suits you">
          {open ? (
            <Lines items={issue.why.filter((line) => !issue.availability_reasons.includes(line))} />
          ) : (
            <p className="text-sm text-ink-2">
              It is not open to start right now. Your daily pick and Explore only show issues
              nobody has taken.
            </p>
          )}
        </Panel>
        <Panel title="What to do first">
          <ol className="list-decimal space-y-1 pl-5 text-sm text-ink-2">
            {issue.checklist.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ol>
          {issue.repo_notes ? <p className="mt-2 text-sm">{issue.repo_notes}</p> : null}
        </Panel>
        <Panel title={`Repo health${issue.health !== null ? `: ${issue.health} of 100` : ""}`}>
          {issue.repo_description ? <p className="mb-2 text-sm">{issue.repo_description}</p> : null}
          <Lines items={issue.health_reasons} />
        </Panel>
        <Panel title="How hard it looks">
          <Lines items={issue.difficulty_reasons} />
          {issue.discussion_first ? (
            <p className="mt-2 text-sm text-warn">Agree on the approach in the issue before coding.</p>
          ) : null}
        </Panel>
        {issue.labels.length ? (
          <Panel title="Labels">
            <ul className="flex flex-wrap gap-2">
              {issue.labels.map((label) => (
                <li key={label} className="rounded-full border border-line px-2 py-0.5 text-xs">
                  {label}
                </li>
              ))}
            </ul>
          </Panel>
        ) : null}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <ComingSoon feature="workspace" title="Start working in one click">
          FirstPR will fork the repo, make a branch and open a ready-to-code workspace for this
          issue, then help you open the pull request.
        </ComingSoon>
        <ComingSoon feature="ai-mentor" title="Mentor">
          Ask for a hint when you are stuck: where the code lives, how to run the tests, what the
          maintainers expect.
        </ComingSoon>
      </div>
    </main>
  );
}
