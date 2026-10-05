"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { timeAgo } from "@/components/issue-bits";
import { useNow } from "@/components/use-now";
import { getJson, sendJson, type Pull, type Pulls } from "@/lib/api";

const DONE = new Set(["merged", "closed_unmerged"]);

function PullCard({ pull }: { pull: Pull }) {
  const [copied, setCopied] = useState(false);
  const tone = pull.needs_you
    ? "border-warn/40 text-warn"
    : DONE.has(pull.status)
      ? "border-line text-ink-2"
      : "border-good/40 text-good";
  return (
    <li className="flex flex-col gap-2 rounded-lg border border-line bg-surface p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-sm text-ink-2">
          {pull.repo} #{pull.number}
        </span>
        <span className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${tone}`}>
          {pull.status_label}
        </span>
        {pull.draft ? <span className="text-xs text-ink-2">Draft</span> : null}
      </div>
      {pull.url ? (
        <a href={pull.url} target="_blank" rel="noreferrer" className="text-lg font-semibold hover:underline">
          {pull.title}
        </a>
      ) : (
        <span className="text-lg font-semibold">{pull.title}</span>
      )}
      <p className={pull.needs_you ? "font-semibold" : "text-ink-2"}>{pull.what_to_do}</p>
      {pull.reasons.length ? (
        <ul className="list-disc pl-5 text-sm text-ink-2">
          {pull.reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      ) : null}
      {pull.timeline.length ? (
        <details className="text-sm">
          <summary className="cursor-pointer text-ink-2">Recent activity</summary>
          <ul className="mt-1 space-y-0.5">
            {pull.timeline.map((t) => (
              <li key={`${t.at}${t.text}`}>
                <span className="text-ink-2">{timeAgo(t.at)}:</span> {t.text}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
      {pull.nudge ? (
        <div className="rounded-md border border-line p-3 text-sm">
          <p className="mb-1 font-semibold">A polite nudge, ready to copy</p>
          <p className="mb-2 text-ink-2">{pull.nudge}</p>
          <button
            type="button"
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(pull.nudge ?? "");
                setCopied(true);
              } catch {
                setCopied(false);
              }
            }}
            className="rounded-md border border-line px-3 py-1 font-semibold"
          >
            {copied ? "Copied. Paste it as a comment on GitHub" : "Copy"}
          </button>
          <p className="mt-1 text-xs text-ink-2">FirstPR never posts it for you.</p>
        </div>
      ) : null}
    </li>
  );
}

function Group({ title, pulls, empty }: { title: string; pulls: Pull[]; empty: string }) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-xl font-semibold">
        {title} <span className="text-ink-2">({pulls.length})</span>
      </h2>
      {pulls.length ? (
        <ul className="flex flex-col gap-3">
          {pulls.map((p) => (
            <PullCard key={`${p.repo}#${p.number}`} pull={p} />
          ))}
        </ul>
      ) : (
        <p className="text-sm text-ink-2">{empty}</p>
      )}
    </section>
  );
}

export default function PullsPage() {
  const queryClient = useQueryClient();
  const now = useNow(15_000);
  const { data, error } = useQuery({
    queryKey: ["pulls"],
    queryFn: () => getJson<Pulls>("/api/v1/me/pulls", "your pull requests"),
    refetchInterval: 60_000,
  });
  const refresh = useMutation({
    mutationFn: () => sendJson<Pulls>("/api/v1/me/pulls/refresh", "check GitHub"),
    onSuccess: (fresh) => {
      queryClient.setQueryData(["pulls"], fresh);
      // The check runs in the background; look again shortly.
      window.setTimeout(() => queryClient.invalidateQueries({ queryKey: ["pulls"] }), 15_000);
    },
  });

  if (error) return <p className="text-warn">{error.message}</p>;
  if (!data) return <p className="text-ink-2">Loading</p>;
  const needs = data.items.filter((p) => p.needs_you);
  const waiting = data.items.filter((p) => !p.needs_you && !DONE.has(p.status));
  const done = data.items.filter((p) => DONE.has(p.status));
  const waitUntil = data.next_refresh_at ? new Date(data.next_refresh_at).getTime() : 0;
  const cooling = waitUntil > now;

  return (
    <main className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold">My pull requests</h1>
          <p className="text-ink-2">
            What needs you first. Checked {timeAgo(data.checked_at)}; GitHub is checked every 2
            hours, and within a minute when a webhook arrives.
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <button
            type="button"
            onClick={() => refresh.mutate()}
            disabled={refresh.isPending || cooling}
            className="rounded-md border border-line px-4 py-2 font-semibold disabled:opacity-50"
          >
            {refresh.isPending ? "Asking GitHub" : "Check now"}
          </button>
          {cooling ? (
            <span className="text-xs text-ink-2">
              Again in {Math.max(1, Math.round((waitUntil - now) / 60_000))} min
            </span>
          ) : null}
        </div>
      </div>
      {refresh.error ? <p className="text-sm text-warn">{refresh.error.message}</p> : null}
      {data.items.length === 0 ? (
        <p className="rounded-lg border border-line bg-surface p-5 text-ink-2">
          No pull requests yet. Ones you open through FirstPR, and your other public pull requests
          from the last 90 days, show up here after the next check.
        </p>
      ) : (
        <>
          <Group title="Needs you" pulls={needs} empty="Nothing needs you right now." />
          <Group title="Waiting on others" pulls={waiting} empty="Nothing waiting." />
          <Group title="Done" pulls={done} empty="Nothing merged or closed yet." />
        </>
      )}
    </main>
  );
}
