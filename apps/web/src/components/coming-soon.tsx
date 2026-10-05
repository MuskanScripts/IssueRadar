"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getJson, sendJson } from "@/lib/api";

// Features that are planned but not built. Each one shows where it will live,
// and "I want this" clicks are counted on the admin page to decide what comes next.
export type Feature =
  | "hosted-workspaces"
  | "vscode-extension"
  | "ai-mentor"
  | "leaderboard"
  | "weekly-challenges"
  | "learned-ranking"
  | "career-paths"
  | "teams";

function useInterest() {
  return useQuery({
    queryKey: ["interest"],
    queryFn: () => getJson<string[]>("/api/v1/me/interest", "your requests"),
    staleTime: 5 * 60_000,
  });
}

export function ComingSoon({
  feature,
  title,
  children,
  compact = false,
}: {
  feature: Feature;
  title: string;
  children: React.ReactNode;
  compact?: boolean;
}) {
  const queryClient = useQueryClient();
  const { data: wanted } = useInterest();
  const want = useMutation({
    mutationFn: () =>
      sendJson<string[]>("/api/v1/me/interest", "save that", { json: { feature } }),
    onSuccess: (data) => queryClient.setQueryData(["interest"], data),
  });
  const asked = wanted?.includes(feature) ?? false;

  return (
    <section
      className={`rounded-lg border border-dashed border-line bg-surface ${compact ? "p-4" : "p-5"}`}
      aria-label={`${title}, coming soon`}
    >
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <h2 className="font-semibold">{title}</h2>
        <span className="rounded-full border border-line px-2 py-0.5 text-xs font-semibold text-ink-2">
          Coming soon
        </span>
      </div>
      <p className="text-sm text-ink-2">{children}</p>
      <button
        type="button"
        onClick={() => want.mutate()}
        disabled={asked || want.isPending}
        className="mt-3 rounded-md border border-line px-3 py-1 text-sm font-semibold disabled:opacity-60"
      >
        {asked ? "Thanks, we counted you" : "I want this"}
      </button>
      {want.error ? <p className="mt-2 text-sm text-warn">{want.error.message}</p> : null}
    </section>
  );
}
