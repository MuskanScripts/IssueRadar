"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { getJson, workspacePath, type WorkspaceList } from "@/lib/api";

const STATUS: Record<string, string> = {
  queued: "Getting ready",
  working: "Setting up",
  ready: "Ready to code",
  failed: "Setup stopped",
  pr_open: "Pull request open",
};

export default function WorkPage() {
  const { data, error } = useQuery({
    queryKey: ["workspaces"],
    queryFn: () => getJson<WorkspaceList>("/api/v1/workspaces", "your work"),
  });
  if (error) return <p className="text-warn">{error.message}</p>;
  if (!data) return <p className="text-ink-2">Loading</p>;

  return (
    <main className="flex flex-col gap-5">
      <div>
        <h1 className="text-3xl font-bold">My work</h1>
        <p className="text-ink-2">
          Issues you are working on. {data.open_prs} of {data.open_pr_limit} pull requests open.
        </p>
      </div>
      {data.practice_repo && !data.practice_done ? (
        <p className="rounded-md border border-accent/40 bg-surface p-3 text-sm">
          Your first pull request goes to the practice repo,{" "}
          <span className="font-mono">{data.practice_repo}</span>. It shows you the whole flow
          without bothering real maintainers. Pick one of its issues in Explore.
        </p>
      ) : null}
      {data.items.length === 0 ? (
        <section className="rounded-lg border border-line bg-surface p-5">
          <p className="text-ink-2">Nothing in progress. Open an issue and click Start working.</p>
          <Link href="/home" className="mt-2 inline-block font-semibold text-accent underline">
            See today&apos;s pick
          </Link>
        </section>
      ) : (
        <ul className="flex flex-col gap-3">
          {data.items.map((ws) => (
            <li key={ws.id} className="flex flex-wrap items-center gap-3 rounded-lg border border-line bg-surface p-4">
              <div className="min-w-0 flex-1">
                <p className="font-mono text-sm text-ink-2">
                  {ws.repo} #{ws.number}
                  {ws.practice ? " · practice" : ""}
                </p>
                <Link href={workspacePath(ws)} className="text-lg font-semibold hover:underline">
                  {ws.issue_title}
                </Link>
              </div>
              <span
                className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${
                  ws.status === "failed" ? "border-warn/40 text-warn" : "border-line text-ink-2"
                }`}
              >
                {STATUS[ws.status] ?? ws.status}
              </span>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
