"use client";

import type { Progress } from "@/lib/api";

/** Today's minutes against the green-day goal, the streak, and XP. */
export function ProgressStrip({ data }: { data: Progress }) {
  const share = Math.min(1, data.today_minutes / data.goal_minutes);
  const green = data.today_minutes >= data.goal_minutes;
  return (
    <div className="grid gap-3 sm:grid-cols-3">
      <div className="rounded-lg border border-line bg-surface p-4">
        <p className="text-sm text-ink-2">Today</p>
        <p className="text-2xl font-bold">
          {data.today_minutes} <span className="text-base font-normal text-ink-2">of {data.goal_minutes} min</span>
        </p>
        <div
          className="mt-2 h-2 rounded-full bg-line"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={data.goal_minutes}
          aria-valuenow={Math.min(data.today_minutes, data.goal_minutes)}
          aria-label="Active minutes today"
        >
          <div className="h-2 rounded-full bg-accent" style={{ width: `${share * 100}%` }} />
        </div>
        <p className="mt-1 text-xs text-ink-2">{green ? "Today is green." : "15 minutes makes today green."}</p>
      </div>
      <div className="rounded-lg border border-line bg-surface p-4">
        <p className="text-sm text-ink-2">Streak</p>
        <p className="text-2xl font-bold">
          {data.streak.current} <span className="text-base font-normal text-ink-2">day{data.streak.current === 1 ? "" : "s"}</span>
        </p>
        <p className="mt-1 text-xs text-ink-2">
          Best {data.streak.best}.{" "}
          {data.streak.freeze_left_this_week
            ? "This week's free freeze is still there."
            : "This week's freeze is used."}
        </p>
      </div>
      <div className="rounded-lg border border-line bg-surface p-4">
        <p className="text-sm text-ink-2">XP</p>
        <p className="text-2xl font-bold">{data.stats.xp}</p>
        <p className="mt-1 text-xs text-ink-2">From merged and approved pull requests only.</p>
      </div>
    </div>
  );
}

export function Badges({ badges }: { badges: Progress["badges"] }) {
  return (
    <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {badges.map((b) => (
        <li
          key={b.key}
          className={`rounded-lg border bg-surface p-4 ${b.earned_at ? "border-accent/50" : "border-line opacity-70"}`}
        >
          <p className="font-semibold">
            <span aria-hidden="true">{b.earned_at ? "★ " : "☆ "}</span>
            {b.name}
            <span className="sr-only">{b.earned_at ? ", earned" : ", not earned yet"}</span>
          </p>
          <p className="text-sm text-ink-2">{b.description}</p>
          {b.earned_at ? (
            <p className="mt-1 text-xs text-ink-2">Earned {new Date(b.earned_at).toLocaleDateString()}</p>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
