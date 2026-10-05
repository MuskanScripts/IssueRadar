"use client";

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { IssueRow, timeAgo } from "@/components/issue-bits";
import { useNow } from "@/components/use-now";
import {
  getJson,
  sendJson,
  type Changes,
  type IssuePage,
  type Options,
  type Profile,
  type RefreshState,
} from "@/lib/api";

type Sort = "fit" | "newest" | "shuffle";
type Filters = { level: string; skill: string; language: string; fresh: string };

const NO_FILTERS: Filters = { level: "", skill: "", language: "", fresh: "" };
// Stop waiting for a refresh to land after this long; the sync keeps going.
const REFRESH_WAIT_MS = 3 * 60_000;

function newSeed() {
  return Math.random().toString(36).slice(2, 10);
}

function Select({
  label,
  value,
  onChange,
  choices,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  choices: [string, string][];
}) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="text-ink-2">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-line bg-surface px-2 py-1.5"
      >
        {choices.map(([key, text]) => (
          <option key={key} value={key}>
            {text}
          </option>
        ))}
      </select>
    </label>
  );
}

export default function ExplorePage() {
  const queryClient = useQueryClient();
  const now = useNow(10_000);
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [sort, setSort] = useState<Sort>("fit");
  const [seed, setSeed] = useState(newSeed);
  const [since, setSince] = useState<string | null>(null);

  const options = useQuery({
    queryKey: ["onboarding-options"],
    queryFn: () => getJson<Options>("/api/v1/onboarding/options", "the filters"),
    staleTime: Infinity,
  });
  const profile = useQuery({
    queryKey: ["profile"],
    queryFn: () => getJson<Profile>("/api/v1/me/profile", "your profile"),
  });

  const params = new URLSearchParams({ sort, seed });
  for (const [key, value] of Object.entries(filters)) if (value) params.set(key, value);
  const issues = useInfiniteQuery({
    queryKey: ["issues", params.toString()],
    queryFn: ({ pageParam }) => {
      const page = new URLSearchParams(params);
      if (pageParam) page.set("cursor", pageParam);
      return getJson<IssuePage>(`/api/v1/issues?${page}`, "issues");
    },
    initialPageParam: "",
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });

  const waiting = since !== null && now - new Date(since).getTime() < REFRESH_WAIT_MS;
  const refreshState = useQuery({
    queryKey: ["refresh-state"],
    queryFn: () => getJson<RefreshState>("/api/v1/me/refresh", "the refresh state"),
    refetchInterval: waiting ? 10_000 : 60_000,
  });
  const landed =
    since !== null &&
    refreshState.data?.data_updated_at != null &&
    new Date(refreshState.data.data_updated_at) > new Date(since);
  const changes = useQuery({
    queryKey: ["changes", since],
    queryFn: () =>
      getJson<Changes>(`/api/v1/issues/changes?since=${encodeURIComponent(since ?? "")}`, "changes"),
    enabled: landed,
  });
  const refresh = useMutation({
    mutationFn: () => sendJson<RefreshState>("/api/v1/me/refresh", "refresh"),
    onSuccess: (state) => {
      queryClient.setQueryData(["refresh-state"], state);
      setSince(state.requested_at);
    },
  });

  const nextAllowed = refreshState.data?.next_allowed_at;
  const coolingDown = nextAllowed != null && new Date(nextAllowed).getTime() > now;
  const items = issues.data?.pages.flatMap((p) => p.items) ?? [];
  const total = issues.data?.pages[0]?.total;
  const set = (key: keyof Filters) => (value: string) => setFilters({ ...filters, [key]: value });
  const mySkills = [...new Set(profile.data?.skills.map((s) => s.name) ?? [])].sort();

  return (
    <main className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold">Explore</h1>
          <p className="text-ink-2">
            Open issues nobody has claimed, best fit first.{" "}
            {refreshState.data?.data_updated_at
              ? `Updated ${timeAgo(refreshState.data.data_updated_at)}.`
              : null}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <button
            type="button"
            onClick={() => refresh.mutate()}
            disabled={refresh.isPending || coolingDown}
            className="rounded-md border border-line px-4 py-2 font-semibold disabled:opacity-50"
          >
            {refresh.isPending ? "Asking GitHub" : "Refresh"}
          </button>
          <span className="text-xs text-ink-2">
            {coolingDown && nextAllowed
              ? `Again in ${Math.max(1, Math.round((new Date(nextAllowed).getTime() - now) / 60_000))} min`
              : "Checks GitHub for new activity"}
          </span>
        </div>
      </div>

      {refresh.error ? <p className="text-sm text-warn">{refresh.error.message}</p> : null}
      {since && !landed && waiting ? (
        <p role="status" className="rounded-md border border-line bg-surface p-3 text-sm">
          Checking GitHub for changes. This page updates when it is done.
        </p>
      ) : null}
      {since && !landed && !waiting ? (
        <p role="status" className="rounded-md border border-line bg-surface p-3 text-sm">
          The check is taking longer than usual. New activity shows up here as it arrives.
        </p>
      ) : null}
      {landed && changes.data ? (
        <div
          role="status"
          className="flex flex-wrap items-center gap-3 rounded-md border border-accent/40 bg-surface p-3 text-sm"
        >
          <span>
            Up to date. {changes.data.new_activity} issue
            {changes.data.new_activity === 1 ? "" : "s"} with new activity,{" "}
            {changes.data.now_taken} claimed by others since you looked.
          </span>
          <button
            type="button"
            onClick={() => {
              setSince(null);
              queryClient.invalidateQueries({ queryKey: ["issues"] });
            }}
            className="font-semibold text-accent underline"
          >
            Show the new list
          </button>
        </div>
      ) : null}

      <div className="flex flex-wrap items-end gap-3 rounded-lg border border-line bg-surface p-3">
        <Select
          label="Level"
          value={filters.level}
          onChange={set("level")}
          choices={[
            ["", "Any level"],
            ["beginner", "Beginner"],
            ["intermediate", "Intermediate"],
            ["pro", "Pro"],
          ]}
        />
        <Select
          label="Your skills"
          value={filters.skill}
          onChange={set("skill")}
          choices={[["", "Any skill"], ...mySkills.map((s): [string, string] => [s, s])]}
        />
        <Select
          label="Language"
          value={filters.language}
          onChange={set("language")}
          choices={[
            ["", "Any language"],
            ...(options.data?.skills.languages ?? []).map((l): [string, string] => [l, l]),
          ]}
        />
        <Select
          label="Updated"
          value={filters.fresh}
          onChange={set("fresh")}
          choices={[
            ["", "Any time"],
            ["7", "This week"],
            ["30", "This month"],
            ["90", "Last 3 months"],
          ]}
        />
        <Select
          label="Order"
          value={sort}
          onChange={(value) => setSort(value as Sort)}
          choices={[
            ["fit", "Best fit"],
            ["newest", "Recently active"],
            ["shuffle", "Shuffled"],
          ]}
        />
        <button
          type="button"
          onClick={() => {
            setSort("shuffle");
            setSeed(newSeed());
          }}
          className="rounded-md border border-line px-3 py-1.5 text-sm font-semibold"
        >
          Shuffle
        </button>
        {Object.values(filters).some(Boolean) ? (
          <button
            type="button"
            onClick={() => setFilters(NO_FILTERS)}
            className="text-sm text-ink-2 underline"
          >
            Clear filters
          </button>
        ) : null}
      </div>

      {issues.error ? <p className="text-warn">{issues.error.message}</p> : null}
      {issues.isPending ? <p className="text-ink-2">Loading issues</p> : null}
      {total !== undefined ? (
        <p className="text-sm text-ink-2">
          {total} issue{total === 1 ? "" : "s"}
        </p>
      ) : null}
      {total === 0 ? (
        <p className="rounded-lg border border-line bg-surface p-5 text-ink-2">
          Nothing matches. Try fewer filters, or Refresh to check GitHub.
        </p>
      ) : null}
      <ul className="flex flex-col gap-3">
        {items.map((issue) => (
          <IssueRow key={`${issue.repo}#${issue.number}`} issue={issue} surface="explore" />
        ))}
      </ul>
      {issues.hasNextPage ? (
        <button
          type="button"
          onClick={() => issues.fetchNextPage()}
          disabled={issues.isFetchingNextPage}
          className="self-center rounded-md border border-line px-4 py-2 font-semibold disabled:opacity-50"
        >
          {issues.isFetchingNextPage ? "Loading" : "Load more"}
        </button>
      ) : null}
    </main>
  );
}
