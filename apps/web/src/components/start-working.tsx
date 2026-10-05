"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ApiError,
  getJson,
  sendJson,
  workspacePath,
  type Workspace,
  type WorkspaceList,
} from "@/lib/api";

/** The Start working panel on an issue page. */
export function StartWorking({ repo, number, open }: { repo: string; number: number; open: boolean }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const list = useQuery({
    queryKey: ["workspaces"],
    queryFn: () => getJson<WorkspaceList>("/api/v1/workspaces", "your work"),
  });
  const start = useMutation({
    mutationFn: (mode: "codespace" | "local") =>
      sendJson<Workspace>("/api/v1/workspaces", "start", { json: { repo, number, mode } }),
    onSuccess: (ws) => {
      queryClient.invalidateQueries({ queryKey: ["workspaces"] });
      queryClient.invalidateQueries({ queryKey: ["today"] });
      router.push(workspacePath(ws));
    },
  });

  const existing = list.data?.items.find(
    (w) => w.repo.toLowerCase() === repo.toLowerCase() && w.number === number,
  );
  const error = start.error instanceof ApiError ? start.error : null;
  const installUrl = error?.code === "install_needed" ? (error.extra.install_url as string | null) : null;

  return (
    <section className="flex flex-col gap-3 rounded-lg border border-accent/40 bg-surface p-5">
      <h2 className="font-semibold">Start working</h2>
      {existing ? (
        <>
          <p className="text-sm text-ink-2">You are already working on this issue.</p>
          <Link
            href={workspacePath(existing)}
            className="self-start rounded-md bg-accent px-4 py-2 font-semibold text-accent-ink hover:opacity-90"
          >
            Open your workspace
          </Link>
        </>
      ) : !open ? (
        <p className="text-sm text-ink-2">This issue is not free, so it cannot be started.</p>
      ) : (
        <>
          <p className="text-sm text-ink-2">
            FirstPR forks the repo to your account, makes a branch for this issue and opens a
            ready-to-code Codespace. The issue is kept for you while you work on it. Nothing is
            posted on the issue or the repo for you.
          </p>
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => start.mutate("codespace")}
              disabled={start.isPending}
              className="rounded-md bg-accent px-4 py-2 font-semibold text-accent-ink hover:opacity-90 disabled:opacity-50"
            >
              {start.isPending && start.variables === "codespace" ? "Starting" : "Start in a Codespace"}
            </button>
            <button
              type="button"
              onClick={() => start.mutate("local")}
              disabled={start.isPending}
              className="rounded-md border border-line px-4 py-2 font-semibold disabled:opacity-50"
            >
              {start.isPending && start.variables === "local" ? "Starting" : "Work on my computer"}
            </button>
          </div>
        </>
      )}
      {error && error.code === "install_needed" ? (
        <div className="rounded-md border border-line p-3 text-sm">
          <p className="mb-2">{error.message}</p>
          {installUrl ? (
            <a
              href={installUrl}
              className="inline-block rounded-md bg-accent px-3 py-1.5 font-semibold text-accent-ink"
            >
              Install FirstPR on GitHub
            </a>
          ) : (
            <p className="text-ink-2">The app&apos;s install link is not set up on this server yet.</p>
          )}
          <p className="mt-2 text-ink-2">
            Choose <strong>All repositories</strong>, so FirstPR can see the fork it makes. You come
            back to this issue afterwards.
          </p>
        </div>
      ) : start.error ? (
        <p className="text-sm text-warn">{start.error.message}</p>
      ) : null}
    </section>
  );
}
