"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ComingSoon } from "@/components/coming-soon";
import {
  ApiError,
  getJson,
  sendJson,
  type PullDraft,
  type PullResult,
  type WorkChanges,
  type Workspace,
  type WorkspaceStep,
} from "@/lib/api";

const SETTING_UP: Workspace["status"][] = ["queued", "working"];

const STEP_MARK: Record<WorkspaceStep["state"], { mark: string; className: string; label: string }> = {
  pending: { mark: "○", className: "text-ink-2", label: "Waiting" },
  running: { mark: "◐", className: "text-accent animate-pulse", label: "In progress" },
  done: { mark: "✓", className: "text-good", label: "Done" },
  failed: { mark: "✕", className: "text-warn", label: "Failed" },
  skipped: { mark: "–", className: "text-ink-2", label: "Skipped" },
};

const STATUS_TEXT: Record<Workspace["status"], string> = {
  queued: "Getting ready",
  working: "Setting up",
  ready: "Ready to code",
  failed: "Setup stopped",
  pr_open: "Pull request open",
  closed: "Closed",
};

/** Follows the setup live over server-sent events; falls back to polling. */
function useLiveWorkspace(id: string) {
  const queryClient = useQueryClient();
  const [streamFailed, setStreamFailed] = useState(false);
  const query = useQuery({
    queryKey: ["workspace", id],
    queryFn: () => getJson<Workspace>(`/api/v1/workspaces/${id}`, "the workspace"),
    refetchInterval: (q) =>
      streamFailed && q.state.data && SETTING_UP.includes(q.state.data.status) ? 3000 : false,
  });
  const settingUp = query.data ? SETTING_UP.includes(query.data.status) : false;

  useEffect(() => {
    if (!settingUp) return;
    const source = new EventSource(`/api/v1/workspaces/${id}/events`);
    source.addEventListener("workspace", (event) => {
      queryClient.setQueryData(["workspace", id], JSON.parse((event as MessageEvent).data));
    });
    source.onerror = () => {
      source.close();
      setStreamFailed(true);
    };
    return () => source.close();
  }, [id, settingUp, queryClient]);

  return query;
}

function Steps({ steps }: { steps: WorkspaceStep[] }) {
  return (
    <ol className="flex flex-col gap-2" aria-label="Setup steps">
      {steps.map((step) => {
        const look = STEP_MARK[step.state];
        return (
          <li key={step.key} className="flex gap-3">
            <span aria-hidden="true" className={`w-4 text-center font-bold ${look.className}`}>
              {look.mark}
            </span>
            <span className="min-w-0">
              <span className="block">
                {step.label}
                <span className="sr-only">: {look.label}</span>
              </span>
              {step.detail ? <span className="block text-sm text-ink-2">{step.detail}</span> : null}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

function LocalSteps({ ws }: { ws: Workspace }) {
  const folder = ws.fork?.split("/")[1] ?? "repo";
  const lines = [
    `git clone ${ws.clone_url}`,
    `cd ${folder}`,
    `git checkout ${ws.branch}`,
    "# make your change, then:",
    "git add -A",
    `git commit -m "Fix #${ws.number}: <what you changed>"`,
    "git push",
  ];
  return (
    <div>
      <h3 className="mb-1 font-semibold">Work on your computer</h3>
      <p className="mb-2 text-sm text-ink-2">
        Your fork and branch are ready. Clone it, make the change, and push to the same branch.
      </p>
      <pre className="overflow-x-auto rounded-md border border-line bg-bg p-3 text-sm">
        <code>{lines.join("\n")}</code>
      </pre>
    </div>
  );
}

function PullRequestForm({ ws, changes }: { ws: Workspace; changes: WorkChanges }) {
  const queryClient = useQueryClient();
  const draft = useQuery({
    queryKey: ["pr-draft", ws.id],
    queryFn: () => getJson<PullDraft>(`/api/v1/workspaces/${ws.id}/pull-request/draft`, "the draft"),
    staleTime: Infinity,
  });
  const [edits, setEdits] = useState<{ title?: string; body?: string; draft: boolean }>({ draft: false });
  const title = edits.title ?? draft.data?.title ?? "";
  const body = edits.body ?? draft.data?.body ?? "";
  const create = useMutation({
    mutationFn: () =>
      sendJson<PullResult>(`/api/v1/workspaces/${ws.id}/pull-request`, "open the pull request", {
        json: { title, body, draft: edits.draft },
      }),
    onSuccess: (result) => {
      queryClient.setQueryData(["workspace", String(ws.id)], result.workspace);
      queryClient.invalidateQueries({ queryKey: ["workspaces"] });
    },
  });
  const blocked = create.error instanceof ApiError ? create.error : null;

  if (create.data && !create.data.opened && create.data.manual_url) {
    return (
      <div className="flex flex-col gap-2 rounded-md border border-line p-4">
        <p>
          GitHub wants you to open this one yourself. The form is filled in with your title and
          description: check it and click <strong>Create pull request</strong> on GitHub.
        </p>
        <a
          href={create.data.manual_url}
          target="_blank"
          rel="noreferrer"
          className="self-start rounded-md bg-accent px-4 py-2 font-semibold text-accent-ink"
        >
          Open the form on GitHub
        </a>
        <p className="text-sm text-ink-2">FirstPR notices the pull request within a few minutes.</p>
      </div>
    );
  }

  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        create.mutate();
      }}
    >
      <h3 className="font-semibold">Create the pull request</h3>
      <p className="text-sm text-ink-2">
        From <span className="font-mono">{draft.data?.head ?? ws.branch}</span> into{" "}
        <span className="font-mono">
          {ws.repo}:{ws.base_branch}
        </span>
        , with {changes.ahead_by} commit{changes.ahead_by === 1 ? "" : "s"}. Nothing is sent until
        you click the button.
        {draft.data?.from_template ? " The description starts from the repo's own template." : ""}
      </p>
      <label className="flex flex-col gap-1 text-sm">
        <span className="font-semibold">Title</span>
        <input
          value={title}
          onChange={(e) => setEdits({ ...edits, title: e.target.value })}
          required
          maxLength={256}
          className="rounded-md border border-line bg-bg px-3 py-2"
        />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        <span className="font-semibold">Description</span>
        <textarea
          value={body}
          onChange={(e) => setEdits({ ...edits, body: e.target.value })}
          rows={10}
          className="rounded-md border border-line bg-bg px-3 py-2 font-mono text-sm"
        />
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={edits.draft}
          onChange={(e) => setEdits({ ...edits, draft: e.target.checked })}
          className="accent-[var(--accent)]"
        />
        Open as a draft (not ready for review yet)
      </label>
      {blocked ? <p className="text-sm text-warn">{blocked.message}</p> : null}
      <button
        type="submit"
        disabled={create.isPending || !title.trim() || draft.isPending}
        className="self-start rounded-md bg-accent px-4 py-2 font-semibold text-accent-ink hover:opacity-90 disabled:opacity-50"
      >
        {create.isPending ? "Opening" : "Create pull request"}
      </button>
    </form>
  );
}

function Finished({ ws }: { ws: Workspace }) {
  const check = useMutation({
    mutationFn: () => getJson<WorkChanges>(`/api/v1/workspaces/${ws.id}/changes`, "your changes"),
  });
  const changes = check.data;
  return (
    <section className="flex flex-col gap-3 rounded-lg border border-line bg-surface p-5">
      <h2 className="font-semibold">Done coding?</h2>
      <p className="text-sm text-ink-2">
        Push your commits to <span className="font-mono">{ws.branch}</span>, then check them here.
      </p>
      <button
        type="button"
        onClick={() => check.mutate()}
        disabled={check.isPending}
        className="self-start rounded-md border border-line px-4 py-2 font-semibold disabled:opacity-50"
      >
        {check.isPending ? "Looking" : changes ? "Check again" : "I finished"}
      </button>
      {check.error ? <p className="text-sm text-warn">{check.error.message}</p> : null}
      {changes && changes.ahead_by === 0 ? (
        <p className="text-sm">
          No commits on <span className="font-mono">{ws.branch}</span> yet. Commit and push, then
          check again.
        </p>
      ) : null}
      {changes && changes.ahead_by > 0 ? (
        <>
          <div>
            <h3 className="mb-1 font-semibold">
              {changes.ahead_by} commit{changes.ahead_by === 1 ? "" : "s"}
            </h3>
            <ul className="text-sm">
              {changes.commits.map((c) => (
                <li key={c.sha}>
                  <span className="font-mono text-ink-2">{c.sha}</span> {c.message}
                </li>
              ))}
            </ul>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <caption className="mb-1 text-left font-semibold">Changed files</caption>
              <thead className="text-xs uppercase tracking-wide text-ink-2">
                <tr>
                  <th className="py-1 pr-4">File</th>
                  <th className="py-1 pr-4">Change</th>
                  <th className="py-1 pr-4 text-right">Added</th>
                  <th className="py-1 text-right">Removed</th>
                </tr>
              </thead>
              <tbody>
                {changes.files.map((f) => (
                  <tr key={f.filename} className="border-t border-line">
                    <td className="py-1 pr-4 font-mono">{f.filename}</td>
                    <td className="py-1 pr-4">{f.status}</td>
                    <td className="py-1 pr-4 text-right text-good">+{f.additions}</td>
                    <td className="py-1 text-right text-warn">-{f.deletions}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {changes.compare_url ? (
            <a href={changes.compare_url} target="_blank" rel="noreferrer" className="text-sm underline">
              See the full diff on GitHub
            </a>
          ) : null}
          {changes.pull_request ? null : <PullRequestForm ws={ws} changes={changes} />}
        </>
      ) : null}
    </section>
  );
}

export default function WorkspacePage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();
  const { data: ws, error } = useLiveWorkspace(id);
  const [deleteCodespace, setDeleteCodespace] = useState(true);
  const retry = useMutation({
    mutationFn: (mode?: "codespace" | "local") =>
      sendJson<Workspace>(`/api/v1/workspaces/${id}/retry`, "try again", { json: { mode } }),
    onSuccess: (data) => queryClient.setQueryData(["workspace", id], data),
  });
  const close = useMutation({
    mutationFn: () =>
      sendJson<Workspace>(`/api/v1/workspaces/${id}/close`, "stop", {
        json: { delete_codespace: deleteCodespace },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workspaces"] });
      queryClient.invalidateQueries({ queryKey: ["today"] });
      router.push("/workspaces");
    },
  });

  if (error) return <p className="text-warn">{error.message}</p>;
  if (!ws) return <p className="text-ink-2">Loading</p>;
  const ready = ws.status === "ready" || ws.status === "pr_open";

  return (
    <main className="flex flex-col gap-5">
      <div>
        <p className="font-mono text-sm text-ink-2">
          {ws.repo} #{ws.number}
          {ws.practice ? " · practice" : ""}
        </p>
        <h1 className="text-3xl font-bold">
          <Link href={`/issues/${ws.repo}/${ws.number}`} className="hover:underline">
            {ws.issue_title}
          </Link>
        </h1>
        <p className="mt-1 text-sm" role="status">
          {STATUS_TEXT[ws.status]}
        </p>
      </div>

      {ws.note ? (
        <div role="alert" className="rounded-md border border-warn/40 border-l-4 border-l-warn bg-surface p-3 text-sm">
          <p>{ws.note}</p>
          {ws.help_url ? (
            <a href={ws.help_url} target="_blank" rel="noreferrer" className="mt-1 inline-block font-semibold underline">
              Open your GitHub App settings
            </a>
          ) : null}
        </div>
      ) : null}

      {ws.pull_request ? (
        <section className="flex flex-wrap items-center gap-3 rounded-lg border border-good/40 bg-surface p-5">
          <div className="min-w-0 flex-1">
            <h2 className="font-semibold">Your pull request is open</h2>
            <p className="text-sm text-ink-2">
              Maintainers review in their own time. Reply to their comments and push fixes to the
              same branch.
            </p>
          </div>
          <a
            href={ws.pull_request.url}
            target="_blank"
            rel="noreferrer"
            className="rounded-md bg-accent px-4 py-2 font-semibold text-accent-ink"
          >
            Open pull request{ws.pull_request.number ? ` #${ws.pull_request.number}` : ""}
          </a>
        </section>
      ) : null}

      <section className="rounded-lg border border-line bg-surface p-5">
        <h2 className="mb-3 font-semibold">Setup</h2>
        <Steps steps={ws.steps} />
        {ws.status === "failed" ? (
          <div className="mt-4 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => retry.mutate(undefined)}
              disabled={retry.isPending}
              className="rounded-md bg-accent px-4 py-2 font-semibold text-accent-ink disabled:opacity-50"
            >
              Try again
            </button>
            {ws.mode === "codespace" ? (
              <button
                type="button"
                onClick={() => retry.mutate("local")}
                disabled={retry.isPending}
                className="rounded-md border border-line px-4 py-2 font-semibold disabled:opacity-50"
              >
                Try without a Codespace
              </button>
            ) : null}
          </div>
        ) : null}
        {retry.error ? <p className="mt-2 text-sm text-warn">{retry.error.message}</p> : null}
      </section>

      {ready ? (
        <section className="flex flex-col gap-4 rounded-lg border border-line bg-surface p-5">
          {ws.codespace?.url && ws.mode === "codespace" ? (
            <div className="flex flex-wrap items-center gap-3">
              <a
                href={ws.codespace.url}
                target="_blank"
                rel="noreferrer"
                className="rounded-md bg-accent px-4 py-2 font-semibold text-accent-ink hover:opacity-90"
              >
                Open your Codespace
              </a>
              <span className="text-sm text-ink-2">
                {ws.codespace.state ? `GitHub says: ${ws.codespace.state}. ` : ""}
                It stops after 15 idle minutes and GitHub deletes it 7 days after that.
              </span>
            </div>
          ) : null}
          {ws.clone_url ? <LocalSteps ws={ws} /> : null}
        </section>
      ) : null}

      {ready ? <Finished ws={ws} /> : null}

      <div className="grid gap-4 md:grid-cols-2">
        <ComingSoon feature="vscode-extension" title="VS Code extension" compact>
          Work in your own VS Code with the issue, the checklist and your time on screen.
        </ComingSoon>
        <ComingSoon feature="hosted-workspaces" title="Hosted workspaces" compact>
          A workspace run by FirstPR, for when Codespaces hours run out or a repo will not start.
        </ComingSoon>
      </div>

      {ws.status !== "closed" ? (
        <section className="rounded-lg border border-line bg-surface p-5">
          <h2 className="mb-1 font-semibold">Stop working on this issue</h2>
          <p className="mb-3 text-sm text-ink-2">
            {ws.pull_request
              ? "Your pull request stays open on GitHub."
              : "The issue goes back to everyone. Your fork and branch stay on GitHub."}
          </p>
          {ws.codespace && ws.codespace.state !== "Deleted" ? (
            <label className="mb-3 flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={deleteCodespace}
                onChange={(e) => setDeleteCodespace(e.target.checked)}
                className="accent-[var(--accent)]"
              />
              Also delete the Codespace (unsaved work in it is lost)
            </label>
          ) : null}
          <button
            type="button"
            onClick={() => close.mutate()}
            disabled={close.isPending}
            className="rounded-md border border-line px-4 py-2 font-semibold disabled:opacity-50"
          >
            {close.isPending ? "Stopping" : "Stop working on it"}
          </button>
          {close.error ? <p className="mt-2 text-sm text-warn">{close.error.message}</p> : null}
        </section>
      ) : null}
    </main>
  );
}
