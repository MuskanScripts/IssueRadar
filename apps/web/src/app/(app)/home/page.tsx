"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { ComingSoon } from "@/components/coming-soon";
import { FitBadge, IssueMeta, StateBadge } from "@/components/issue-bits";
import { timeLeft, useNow } from "@/components/use-now";
import { getJson, issuePath, logEvent, sendJson, type Today } from "@/lib/api";
import { useMe } from "../auth-gate";

export default function HomePage() {
  const { data: me } = useMe();
  const queryClient = useQueryClient();
  const now = useNow();
  const { data, error } = useQuery({
    queryKey: ["today"],
    queryFn: () => getJson<Today>("/api/v1/me/today", "today's pick"),
  });
  const another = useMutation({
    mutationFn: () => sendJson<Today>("/api/v1/me/today/another", "find another issue"),
    onSuccess: (today) => queryClient.setQueryData(["today"], today),
  });

  const pick = data?.pick;
  return (
    <main className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold">Hi {me?.name ?? me?.handle}</h1>
          <p className="text-ink-2">One issue a day, picked for you and held for 48 hours.</p>
        </div>
        <Link href="/onboarding" className="text-sm text-ink-2 underline">
          Change your level and skills
        </Link>
      </div>

      {error ? <p className="text-warn">{error.message}</p> : null}
      {!data && !error ? <p className="text-ink-2">Finding today&apos;s pick</p> : null}

      {data && !pick ? (
        <section className="rounded-lg border border-line bg-surface p-6">
          <h2 className="mb-1 text-xl font-semibold">No pick right now</h2>
          <p className="text-ink-2">{data.empty_reason}</p>
          <Link href="/explore" className="mt-3 inline-block font-semibold text-accent underline">
            Browse issues in Explore
          </Link>
        </section>
      ) : null}

      {pick ? (
        <section
          aria-labelledby="pick-title"
          className="flex flex-col gap-4 rounded-lg border border-accent/40 bg-surface p-6"
        >
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold uppercase tracking-wide text-accent">
              Today&apos;s pick
            </span>
            <StateBadge issue={pick} />
            <FitBadge fit={pick.fit} />
            {data?.held_until ? (
              <span className="ml-auto text-sm text-ink-2" title="Nobody else gets this issue until then">
                Held for you for {timeLeft(data.held_until, now)}
              </span>
            ) : null}
          </div>
          <div>
            <p className="font-mono text-sm text-ink-2">
              {pick.repo} #{pick.number}
            </p>
            <h2 id="pick-title" className="text-2xl font-bold">
              <Link
                href={issuePath(pick)}
                onClick={() => logEvent(pick, "daily", "opened")}
                className="hover:underline"
              >
                {pick.title}
              </Link>
            </h2>
          </div>
          <IssueMeta issue={pick} />
          <div>
            <h3 className="mb-1 font-semibold">Why we picked this</h3>
            <ul className="list-disc space-y-1 pl-5 text-ink-2">
              {pick.why.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Link
              href={issuePath(pick)}
              onClick={() => logEvent(pick, "daily", "opened")}
              className="rounded-md bg-accent px-4 py-2 font-semibold text-accent-ink hover:opacity-90"
            >
              Open the issue
            </Link>
            <button
              type="button"
              onClick={() => another.mutate()}
              disabled={another.isPending || data?.swaps_left === 0}
              className="rounded-md border border-line px-4 py-2 font-semibold disabled:opacity-50"
            >
              {another.isPending ? "Finding another" : "Show me another"}
            </button>
            <span className="text-sm text-ink-2">
              {data?.swaps_left === 0
                ? "No more swaps today. A new pick arrives tomorrow."
                : `${data?.swaps_left} swap${data?.swaps_left === 1 ? "" : "s"} left today`}
            </span>
          </div>
          {another.error ? <p className="text-sm text-warn">{another.error.message}</p> : null}
        </section>
      ) : null}

      <ComingSoon feature="learned-ranking" title="Picks that learn from you" compact>
        Picks will get better as FirstPR learns which issues you open, skip and finish.
      </ComingSoon>
    </main>
  );
}
