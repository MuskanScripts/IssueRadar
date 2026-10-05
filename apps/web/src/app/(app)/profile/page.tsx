"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ActivityCalendar } from "@/components/activity-calendar";
import { timeAgo } from "@/components/issue-bits";
import {
  getJson,
  post,
  problem as problemText,
  send,
  sendJson,
  type Profile,
  type Progress,
  type Pulls,
} from "@/lib/api";
import { useMe } from "../auth-gate";

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-line bg-surface p-4">
      <p className="text-sm text-ink-2">{label}</p>
      <p className="text-2xl font-bold">{value}</p>
    </div>
  );
}

export default function ProfilePage() {
  const { data: me } = useMe();
  const queryClient = useQueryClient();
  const router = useRouter();
  const [signingOut, setSigningOut] = useState(false);
  const [problem, setProblem] = useState("");
  const progress = useQuery({
    queryKey: ["progress", 53],
    queryFn: () => getJson<Progress>("/api/v1/me/progress?weeks=53", "your progress"),
  });
  const profile = useQuery({
    queryKey: ["profile"],
    queryFn: () => getJson<Profile>("/api/v1/me/profile", "your profile"),
  });
  const pulls = useQuery({
    queryKey: ["pulls"],
    queryFn: () => getJson<Pulls>("/api/v1/me/pulls", "your pull requests"),
  });
  const visibility = useMutation({
    mutationFn: (pub: boolean) =>
      sendJson<{ public: boolean }>("/api/v1/me/profile/visibility", "save", {
        method: "PUT",
        json: { public: pub },
      }),
    onMutate: (pub) => {
      const before = queryClient.getQueryData<Profile>(["profile"]);
      if (before) queryClient.setQueryData(["profile"], { ...before, public: pub });
      return { before };
    },
    onError: (_e, _v, context) => {
      if (context?.before) queryClient.setQueryData(["profile"], context.before);
    },
  });

  async function signOut() {
    setSigningOut(true);
    const resp = await post("/api/v1/auth/logout");
    if (resp.ok) {
      queryClient.clear();
      router.replace("/");
      return;
    }
    setSigningOut(false);
    setProblem("Signing out did not work. Refresh the page and try again.");
  }

  if (!me) return null;
  const merged = (pulls.data?.items ?? []).filter((p) => p.status === "merged");
  const stats = progress.data?.stats;

  return (
    <main className="flex flex-col gap-6">
      <section className="flex flex-wrap items-center gap-4 rounded-lg border border-line bg-surface p-5">
        {me.avatar_url ? (
          // eslint-disable-next-line @next/next/no-img-element -- small GitHub avatar
          <img src={me.avatar_url} alt="" width={72} height={72} className="rounded-full" />
        ) : null}
        <div className="min-w-0 flex-1">
          <h1 className="text-3xl font-bold">{me.name ?? me.handle}</h1>
          <p className="font-mono text-sm text-ink-2">@{me.handle}</p>
        </div>
        {stats ? (
          <p className="text-right">
            <span className="block text-2xl font-bold">{stats.xp} XP</span>
            <span className="text-sm text-ink-2">
              {progress.data?.streak.current} day streak
            </span>
          </p>
        ) : null}
      </section>

      {stats ? (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="Merged pull requests" value={stats.merged} />
          <Stat label="Repos contributed to" value={stats.repos} />
          <Stat label="Open pull requests" value={stats.open_prs} />
          <Stat label="Best streak" value={progress.data?.streak.best ?? 0} />
        </div>
      ) : null}

      {progress.data ? (
        <section className="rounded-lg border border-line bg-surface p-5">
          <h2 className="mb-2 font-semibold">Activity</h2>
          <ActivityCalendar days={progress.data.calendar} today={progress.data.today} />
        </section>
      ) : null}

      <section className="rounded-lg border border-line bg-surface p-5">
        <h2 className="mb-2 font-semibold">Merged pull requests</h2>
        {merged.length ? (
          <ul className="flex flex-col gap-1 text-sm">
            {merged.map((p) => (
              <li key={`${p.repo}#${p.number}`} className="flex flex-wrap justify-between gap-2">
                <a href={p.url ?? "#"} target="_blank" rel="noreferrer" className="hover:underline">
                  <span className="font-mono text-ink-2">{p.repo} #{p.number}</span> {p.title}
                </a>
                <span className="text-ink-2">{timeAgo(p.closed_at)}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-ink-2">None yet. Your first one shows up here.</p>
        )}
      </section>

      <div className="grid gap-4 md:grid-cols-2">
        <section className="rounded-lg border border-line bg-surface p-5">
          <h2 className="mb-2 font-semibold">Skills</h2>
          {profile.data?.skills.length ? (
            <ul className="flex flex-wrap gap-2">
              {profile.data.skills.map((s) => (
                <li key={`${s.kind}${s.name}`} className="rounded-full border border-line px-3 py-1 text-sm">
                  {s.name} · {s.level}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-ink-2">No skills chosen yet.</p>
          )}
          <Link href="/onboarding" className="mt-3 inline-block text-sm underline">
            Change level and skills
          </Link>
        </section>

        <section className="rounded-lg border border-line bg-surface p-5">
          <h2 className="mb-3 font-semibold">Connected GitHub account</h2>
          <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
            <dt className="text-ink-2">Account</dt>
            <dd className="font-mono">@{me.github.login}</dd>
            <dt className="text-ink-2">Status</dt>
            <dd className={me.github.status === "connected" ? "text-good" : "text-warn"}>
              {me.github.status === "connected" ? "Connected" : "Reconnect needed"}
            </dd>
            <dt className="text-ink-2">Email</dt>
            <dd>{me.email ?? "Not shared"}</dd>
          </dl>
        </section>
      </div>

      <section className="rounded-lg border border-line bg-surface p-5">
        <h2 className="mb-1 font-semibold">Who can see this profile</h2>
        <label className="flex items-start gap-3">
          <input
            type="checkbox"
            checked={profile.data?.public ?? false}
            disabled={!profile.data}
            onChange={(e) => visibility.mutate(e.target.checked)}
            className="mt-1 accent-[var(--accent)]"
          />
          <span>
            <span className="block font-semibold">Public profile</span>
            <span className="text-sm text-ink-2">
              Anyone with the link can see your stats, calendar, badges and merged pull requests.
              Off means only you can.
            </span>
          </span>
        </label>
        {visibility.error ? <p className="mt-2 text-sm text-warn">{visibility.error.message}</p> : null}
      </section>

      <DeleteAccount handle={me.handle} />

      <section className="flex flex-wrap items-center gap-3 rounded-lg border border-line bg-surface p-5">
        <Link href="/settings" className="rounded-md border border-line px-4 py-2 font-semibold">
          Settings
        </Link>
        <button
          type="button"
          onClick={signOut}
          disabled={signingOut}
          className="rounded-md border border-line px-4 py-2 font-semibold disabled:opacity-50"
        >
          {signingOut ? "Signing out" : "Sign out"}
        </button>
        {problem ? <p className="text-sm text-warn">{problem}</p> : null}
      </section>
    </main>
  );
}

function DeleteAccount({ handle }: { handle: string }) {
  const queryClient = useQueryClient();
  const router = useRouter();
  const [typed, setTyped] = useState("");
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);

  async function remove() {
    setBusy(true);
    const resp = await send("/api/v1/me", { method: "DELETE", json: { confirm: typed } });
    if (resp.ok) {
      queryClient.clear();
      router.replace("/?signin=deleted");
      return;
    }
    setBusy(false);
    setProblem(await problemText(resp, "Deleting did not work"));
  }

  return (
    <section className="rounded-lg border border-warn/40 bg-surface p-5">
      <h2 className="mb-1 font-semibold">Delete my account</h2>
      <p className="mb-3 text-sm text-ink-2">
        Deletes everything FirstPR stores about you, at once: profile, skills, picks, workspaces,
        pull request tracking, notifications, XP, badges and activity. Your forks, branches,
        Codespaces and pull requests on GitHub are yours and stay there. To also take back
        FirstPR&apos;s access, revoke the app at github.com/settings/applications.
      </p>
      <label className="flex flex-col gap-1 text-sm">
        <span>
          Type <span className="font-mono font-semibold">{handle}</span> to confirm
        </span>
        <input
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          autoComplete="off"
          className="max-w-xs rounded-md border border-line bg-bg px-3 py-2 font-mono"
        />
      </label>
      <button
        type="button"
        onClick={remove}
        disabled={busy || typed.trim().toLowerCase() !== handle.toLowerCase()}
        className="mt-3 rounded-md border border-warn px-4 py-2 font-semibold text-warn disabled:opacity-40"
      >
        {busy ? "Deleting" : "Delete my account and data"}
      </button>
      {problem ? <p className="mt-2 text-sm text-warn">{problem}</p> : null}
    </section>
  );
}
