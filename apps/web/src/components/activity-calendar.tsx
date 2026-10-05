"use client";

import { useEffect, useRef, useState } from "react";
import type { ActivityDay } from "@/lib/api";

const CELL = 12;
const GAP = 3;
const STEP = CELL + GAP;
const LEFT = 30; // room for weekday labels
const TOP = 16; // room for month labels
const DAY_NAMES = ["Mon", "", "Wed", "", "Fri", "", ""];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** One hue, light to dark. Level 3 is where a day turns green (15 minutes). */
function level(day: ActivityDay): 0 | 1 | 2 | 3 | 4 {
  if (day.minutes >= 30) return 4;
  if (day.green) return 3;
  if (day.minutes >= 5) return 2;
  if (day.minutes >= 1) return 1;
  return 0;
}

const FILL = ["var(--line)", "var(--heat-1)", "var(--heat-2)", "var(--heat-3)", "var(--heat-4)"];

function parse(day: string) {
  const [y, m, d] = day.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}

function describe(day: ActivityDay) {
  const when = parse(day.day).toLocaleDateString(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
  const parts = [`${day.minutes} active min`];
  if (day.codespace_minutes) parts.push(`${day.codespace_minutes} in a Codespace`);
  if (day.commits) parts.push(`${day.commits} commit${day.commits === 1 ? "" : "s"}`);
  const state = day.frozen ? "streak freeze used" : day.green ? "green" : "";
  return `${when}: ${parts.join(", ")}${state ? ` (${state})` : ""}`;
}

/** The activity calendar: one column per week, Monday at the top. */
export function ActivityCalendar({ days, today }: { days: ActivityDay[]; today: string }) {
  const [hover, setHover] = useState<{ text: string; x: number; y: number } | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  // On narrow screens, start scrolled to the newest weeks.
  useEffect(() => {
    if (scroller.current) scroller.current.scrollLeft = scroller.current.scrollWidth;
  }, [days.length]);
  const weeks = Math.ceil(days.length / 7);
  const width = LEFT + weeks * STEP;
  const height = TOP + 7 * STEP;
  const greenDays = days.filter((d) => d.green).length;

  const months: { x: number; label: string }[] = [];
  for (let w = 0; w < weeks; w++) {
    const first = days[w * 7];
    if (!first) continue;
    const date = parse(first.day);
    const prev = w > 0 ? parse(days[(w - 1) * 7].day) : null;
    if (!prev || prev.getUTCMonth() !== date.getUTCMonth()) {
      months.push({ x: LEFT + w * STEP, label: MONTHS[date.getUTCMonth()] });
    }
  }

  return (
    <figure className="flex flex-col gap-2">
      <figcaption className="text-sm text-ink-2">
        {greenDays} green day{greenDays === 1 ? "" : "s"} in the last {weeks} weeks. A day turns
        green at 15 active minutes or a pushed commit.
      </figcaption>
      <div ref={scroller} className="relative overflow-x-auto">
        <svg
          width={width}
          height={height}
          role="img"
          aria-label={`Activity calendar, ${greenDays} green days`}
          className="block"
          onMouseLeave={() => setHover(null)}
        >
          {months.map((m, i) =>
            // Skip a label that would overlap the one before it.
            i > 0 && m.x - months[i - 1].x < 3 * STEP ? null : (
              <text key={`${m.label}${m.x}`} x={m.x} y={10} className="fill-[var(--ink-2)] text-[10px]">
                {m.label}
              </text>
            ),
          )}
          {DAY_NAMES.map((name, i) =>
            name ? (
              <text key={name} x={0} y={TOP + i * STEP + CELL - 2} className="fill-[var(--ink-2)] text-[10px]">
                {name}
              </text>
            ) : null,
          )}
          {days.map((day, i) => {
            const x = LEFT + Math.floor(i / 7) * STEP;
            const y = TOP + (i % 7) * STEP;
            const isToday = day.day === today;
            return (
              <rect
                key={day.day}
                x={x}
                y={y}
                width={CELL}
                height={CELL}
                rx={2}
                fill={day.frozen ? "var(--surface)" : FILL[level(day)]}
                stroke={day.frozen ? "var(--accent)" : isToday ? "var(--ink)" : "none"}
                strokeWidth={day.frozen || isToday ? 1.5 : 0}
                strokeDasharray={day.frozen ? "2 2" : undefined}
                onMouseEnter={() => setHover({ text: describe(day), x, y })}
              />
            );
          })}
        </svg>
        {hover ? (
          <div
            role="status"
            className="pointer-events-none absolute z-10 whitespace-nowrap rounded-md border border-line bg-surface px-2 py-1 text-xs shadow"
            style={{ left: Math.min(hover.x, width - 220), top: Math.max(0, hover.y - 30) }}
          >
            {hover.text}
          </div>
        ) : null}
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-2">
        <span className="flex items-center gap-1">
          Less
          {FILL.map((fill) => (
            <span key={fill} className="inline-block h-3 w-3 rounded-sm" style={{ background: fill }} />
          ))}
          More
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-3 w-3 rounded-sm border border-dashed border-accent" />
          Streak freeze used
        </span>
      </div>
      <details className="text-sm">
        <summary className="cursor-pointer text-ink-2">Show as a table</summary>
        <div className="max-h-64 overflow-y-auto">
          <table className="mt-2 w-full text-left">
            <thead className="text-xs uppercase tracking-wide text-ink-2">
              <tr>
                <th className="py-1 pr-3">Day</th>
                <th className="py-1 pr-3 text-right">Minutes</th>
                <th className="py-1 pr-3 text-right">Codespace</th>
                <th className="py-1 pr-3 text-right">Commits</th>
                <th className="py-1">State</th>
              </tr>
            </thead>
            <tbody>
              {[...days]
                .reverse()
                .filter((d) => d.minutes || d.commits || d.frozen)
                .map((d) => (
                  <tr key={d.day} className="border-t border-line">
                    <td className="py-1 pr-3">{d.day}</td>
                    <td className="py-1 pr-3 text-right">{d.minutes}</td>
                    <td className="py-1 pr-3 text-right">{d.codespace_minutes}</td>
                    <td className="py-1 pr-3 text-right">{d.commits}</td>
                    <td className="py-1">{d.frozen ? "Freeze" : d.green ? "Green" : ""}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}
