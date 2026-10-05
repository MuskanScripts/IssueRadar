"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { getSyncOverview, send, type SyncOverview } from "@/lib/api";

const STATUS_STYLE: Record<string, string> = {
  synced: "text-good",
  archived: "text-ink-2",
  failed: "text-warn",
  paused: "text-warn",
};

function when(iso: string | null) {
  if (!iso) return "never";
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  return hours < 48 ? `${hours} h ago` : `${Math.round(hours / 24)} days ago`;
}

function Budgets({ budgets }: { budgets: SyncOverview["budgets"] }) {
  const entries = Object.entries(budgets);
  if (!entries.length) return <p className="text-sm text-ink-2">No sync has run yet.</p>;
  return (
    <ul className="grid gap-1 text-sm">
      {entries.map(([name, b]) => (
        <li key={name} className="flex justify-between gap-4">
          <span className="font-mono">{name}</span>
          <span className={b.paused ? "text-warn" : ""}>
            {b.remaining ?? "?"} of {b.limit ?? "?"} left{b.paused ? ", paused" : ""}
          </span>
        </li>
      ))}
    </ul>
  );
}

export default function AdminPage() {
  const queryClient = useQueryClient();
  const { data, error, isFetching, refetch } = useQuery({
    queryKey: ["admin-sync"],
    queryFn: getSyncOverview,
    refetchInterval: 30_000,
  });
  const [repo, setRepo] = useState("");
  const [problem, setProblem] = useState("");

  const add = useMutation({
    mutationFn: async (name: string) => {
      const resp = await send("/api/v1/admin/catalogue", { json: { repo: name } });
      if (!resp.ok) throw new Error((await resp.json()).detail ?? `Failed (${resp.status})`);
    },
    onSuccess: () => {
      setRepo("");
      setProblem("");
      queryClient.invalidateQueries({ queryKey: ["admin-sync"] });
    },
    onError: (e: Error) => setProblem(e.message),
  });
  const remove = useMutation({
    mutationFn: (name: string) => send(`/api/v1/admin/catalogue/${name}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-sync"] }),
  });

  if (error) return <p className="text-warn">{error.message}</p>;
  if (!data) return <p className="text-ink-2">Loading</p>;
  const failing = data.repos.filter((r) => r.status === "failed" || r.status === "paused").length;

  return (
    <main className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">Sync</h1>
          <p className="text-ink-2">
            {data.repos.length} repos, {failing} need attention. Refreshes every 30 seconds.
          </p>
        </div>
        <button
          type="button"
          onClick={() => refetch()}
          disabled={isFetching}
          className="rounded-md border border-line px-3 py-1 text-sm font-semibold disabled:opacity-50"
        >
          {isFetching ? "Checking" : "Refresh"}
        </button>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <section className="rounded-lg border border-line bg-surface p-4">
          <h2 className="mb-1 font-semibold">Worker</h2>
          <p className={data.worker === "ok" ? "text-good" : "text-warn"}>{data.worker}</p>
        </section>
        <section className="rounded-lg border border-line bg-surface p-4">
          <h2 className="mb-1 font-semibold">GitHub budgets</h2>
          <Budgets budgets={data.budgets} />
        </section>
        <section className="rounded-lg border border-line bg-surface p-4">
          <h2 className="mb-1 font-semibold">Webhooks</h2>
          <p className="text-sm">{data.webhooks_last_hour} in the last hour</p>
          <p className={`text-sm ${data.webhooks_waiting ? "text-warn" : "text-ink-2"}`}>
            {data.webhooks_waiting} waiting
          </p>
        </section>
      </div>

      <section className="rounded-lg border border-line bg-surface p-4">
        <h2 className="mb-2 font-semibold">Add to the catalogue</h2>
        <form
          className="flex flex-wrap gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (repo.trim()) add.mutate(repo.trim());
          }}
        >
          <input
            id="catalogue-repo"
            aria-label="Repository"
            value={repo}
            onChange={(e) => setRepo(e.target.value)}
            placeholder="owner/name"
            className="min-w-0 flex-1 rounded-md border border-line bg-bg px-3 py-2 font-mono text-sm"
          />
          <button
            type="submit"
            disabled={add.isPending}
            className="rounded-md bg-accent px-4 py-2 font-semibold text-accent-ink disabled:opacity-50"
          >
            Add
          </button>
        </form>
        {problem ? <p className="mt-2 text-sm text-warn">{problem}</p> : null}
      </section>

      <section className="overflow-x-auto rounded-lg border border-line bg-surface">
        <table className="w-full text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-ink-2">
            <tr>
              <th className="px-4 py-2">Repo</th>
              <th className="px-4 py-2">Token</th>
              <th className="px-4 py-2">Watchers</th>
              <th className="px-4 py-2">Status</th>
              <th className="px-4 py-2">Open issues</th>
              <th className="px-4 py-2">Last sync</th>
              <th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody>
            {data.repos.map((r) => (
              <tr key={r.full_name} className="border-t border-line align-top">
                <td className="px-4 py-2 font-mono">{r.full_name}</td>
                <td className="px-4 py-2">{r.token === "app" ? "app" : "watcher's own"}</td>
                <td className="px-4 py-2 tabular-nums">{r.watchers}</td>
                <td className="px-4 py-2">
                  <span className={STATUS_STYLE[r.status ?? ""] ?? "text-ink-2"}>
                    {r.status ?? "not synced yet"}
                  </span>
                  {r.note ? <div className="text-xs text-ink-2">{r.note}</div> : null}
                </td>
                <td className="px-4 py-2 tabular-nums">{r.open_issues ?? ""}</td>
                <td className="px-4 py-2 whitespace-nowrap">{when(r.synced_at)}</td>
                <td className="px-4 py-2">
                  {r.in_catalogue ? (
                    <button
                      type="button"
                      onClick={() => remove.mutate(r.full_name)}
                      className="text-xs text-ink-2 underline hover:text-warn"
                    >
                      Remove
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </main>
  );
}
