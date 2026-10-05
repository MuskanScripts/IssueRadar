"use client";

import { useQuery } from "@tanstack/react-query";
import { ActivityCalendar } from "@/components/activity-calendar";
import { ComingSoon } from "@/components/coming-soon";
import { timeAgo } from "@/components/issue-bits";
import { Badges, ProgressStrip } from "@/components/progress-bits";
import { getJson, type Progress } from "@/lib/api";

export default function ProgressPage() {
  const { data, error } = useQuery({
    queryKey: ["progress", 53],
    queryFn: () => getJson<Progress>("/api/v1/me/progress?weeks=53", "your progress"),
    refetchInterval: 120_000,
  });
  if (error) return <p className="text-warn">{error.message}</p>;
  if (!data) return <p className="text-ink-2">Loading</p>;
  const s = data.stats;
  return (
    <main className="flex flex-col gap-6">
      <div>
        <h1 className="text-3xl font-bold">Progress</h1>
        <p className="text-ink-2">
          {s.merged} merged pull request{s.merged === 1 ? "" : "s"} in {s.repos} repo
          {s.repos === 1 ? "" : "s"}, {s.open_prs} open, {s.started} issue{s.started === 1 ? "" : "s"} started.
        </p>
      </div>
      <ProgressStrip data={data} />
      <section className="rounded-lg border border-line bg-surface p-5">
        <h2 className="mb-2 font-semibold">The last year</h2>
        <ActivityCalendar days={data.calendar} today={data.today} />
      </section>
      <section className="flex flex-col gap-3">
        <h2 className="text-xl font-semibold">Badges</h2>
        <Badges badges={data.badges} />
      </section>
      <section className="rounded-lg border border-line bg-surface p-5">
        <h2 className="mb-2 font-semibold">Recent XP</h2>
        {data.recent_xp.length ? (
          <ul className="flex flex-col gap-1 text-sm">
            {data.recent_xp.map((x) => (
              <li key={`${x.created_at}${x.note}`} className="flex justify-between gap-4">
                <span>{x.note}</span>
                <span className="whitespace-nowrap text-ink-2">
                  +{x.amount} · {timeAgo(x.created_at)}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-ink-2">
            XP comes from accepted work only: +100 for a merged pull request, +20 when one is
            approved, +30 for the practice task.
          </p>
        )}
      </section>
      <div className="grid gap-4 md:grid-cols-2">
        <ComingSoon feature="leaderboard" title="Contribution rating" compact>
          A rating that grows with merged work on harder issues and healthier repos.
        </ComingSoon>
        <ComingSoon feature="weekly-challenges" title="Weekly challenges" compact>
          One small challenge a week on a practice repo, the same for everyone.
        </ComingSoon>
      </div>
    </main>
  );
}
