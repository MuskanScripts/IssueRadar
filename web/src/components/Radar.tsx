import { motion, useReducedMotion } from "framer-motion";
import { useMemo, useState } from "react";

import type { Issue, Tier } from "@/lib/types";

// Rings are the tiers (inner Beginner, outer Pro), angle groups by language,
// dot size is repo health, amber dots are free. Mouse only: the list next to
// the radar is the keyboard equivalent, so the SVG is hidden from screen readers.

const SIZE = 640;
const C = SIZE / 2;
const BANDS: Record<Tier, [number, number]> = {
  beginner: [36, 118],
  intermediate: [128, 210],
  pro: [220, 292],
};
const RINGS = [118, 210, 292];
const MAX_SECTORS = 8;
const SWEEP_SECONDS = 1.6;
let swept = false; // the sweep plays once per page load, then the radar stays still

function claimSweep(): boolean {
  if (swept) return false;
  swept = true;
  return true;
}

function hash(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619);
  return ((h >>> 0) % 1000) / 1000;
}

interface Dot {
  issue: Issue;
  x: number;
  y: number;
  r: number;
  angle: number;
}

export function layout(issues: Issue[]): { dots: Dot[]; sectors: { label: string; angle: number }[] } {
  const counts = new Map<string, number>();
  for (const i of issues) {
    const key = (i.language ?? "other").toLowerCase();
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  const ranked = [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  const named = ranked.slice(0, MAX_SECTORS - (ranked.length > MAX_SECTORS ? 1 : 0)).map(([k]) => k);
  const groups = ranked.length > named.length ? [...named, "other"] : named;
  const span = (Math.PI * 2) / Math.max(groups.length, 1);
  const sectors = groups.map((label, index) => ({ label, angle: index * span + span / 2 }));
  const dots = issues.map((issue) => {
    const lang = (issue.language ?? "other").toLowerCase();
    const index = Math.max(groups.indexOf(named.includes(lang) ? lang : "other"), 0);
    const [inner, outer] = BANDS[issue.tier];
    const within = issue.tier === "beginner" ? issue.difficulty_score / 33
      : issue.tier === "intermediate" ? (issue.difficulty_score - 34) / 32
      : (issue.difficulty_score - 67) / 33;
    const radius = inner + Math.min(Math.max(within, 0.05), 0.95) * (outer - inner);
    const angle = index * span + span * (0.15 + 0.7 * hash(`${issue.repo}#${issue.number}`));
    return {
      issue,
      angle,
      x: C + radius * Math.sin(angle),
      y: C - radius * Math.cos(angle),
      r: 4 + ((issue.health ?? 50) / 100) * 6,
    };
  });
  return { dots, sectors };
}

export function Radar({ issues, onSelect }: { issues: Issue[]; onSelect(issue: Issue): void }) {
  const reduce = useReducedMotion();
  const [animate] = useState(() => claimSweep() && !reduce);
  const { dots, sectors } = useMemo(() => layout(issues), [issues]);
  const [hover, setHover] = useState<Dot | null>(null);
  const free = issues.filter((i) => i.availability === "free").length;

  return (
    <div className="relative mx-auto w-full max-w-[640px]">
      <svg
        viewBox={`-70 -20 ${SIZE + 140} ${SIZE + 40}`}
        className="h-auto w-full"
        role="img"
        aria-label={`Radar of ${issues.length} issues, ${free} free. The list next to it has the same issues.`}
      >
        {RINGS.map((r) => (
          <circle key={r} cx={C} cy={C} r={r} fill="none" stroke="var(--radar-ring)" strokeWidth={1.5} />
        ))}
        {sectors.map((s) => {
          const x = C + 300 * Math.sin(s.angle - Math.PI / sectors.length);
          const y = C - 300 * Math.cos(s.angle - Math.PI / sectors.length);
          return sectors.length > 1 ? (
            <line key={`l-${s.label}`} x1={C} y1={C} x2={x} y2={y} stroke="var(--rule-soft)" strokeWidth={1} />
          ) : null;
        })}
        {[
          ["Beginner", 118],
          ["Intermediate", 210],
          ["Pro", 292],
        ].map(([label, r]) => (
          <text
            key={label}
            x={C + 6}
            y={C - (r as number) + 16}
            className="fill-ink-muted font-mono text-[12px]"
            stroke="var(--ground)"
            strokeWidth={4}
            paintOrder="stroke"
          >
            {label}
          </text>
        ))}
        {sectors.map((s) => (
          <text
            key={s.label}
            x={C + 306 * Math.sin(s.angle)}
            y={C - 306 * Math.cos(s.angle) + 4}
            textAnchor={Math.sin(s.angle) > 0.25 ? "start" : Math.sin(s.angle) < -0.25 ? "end" : "middle"}
            className="fill-ink-secondary font-mono text-[13px]"
          >
            {s.label}
          </text>
        ))}
        {animate ? (
          <motion.g
            style={{ originX: `${C}px`, originY: `${C}px` }}
            initial={{ rotate: 0, opacity: 1 }}
            animate={{ rotate: 360, opacity: 0 }}
            transition={{ rotate: { duration: SWEEP_SECONDS, ease: "linear" }, opacity: { delay: SWEEP_SECONDS, duration: 0.3 } }}
          >
            <path d={`M${C} ${C}L${C} ${C - 300}A300 300 0 0 1 ${C + 260} ${C - 150}Z`} fill="var(--action)" fillOpacity={0.1} />
          </motion.g>
        ) : null}
        {dots.map((dot) => {
          const key = `${dot.issue.repo}#${dot.issue.number}`;
          const state = dot.issue.availability;
          const fill = state === "free" ? "var(--amber)" : state === "likely_free" ? "var(--amber-tint)" : "transparent";
          const stroke = state === "free" ? "var(--on-amber)" : state === "likely_free" ? "var(--amber)" : "var(--ink-muted)";
          return (
            <motion.g
              key={key}
              initial={animate ? { opacity: 0 } : false}
              animate={{ opacity: 1 }}
              transition={{ delay: animate ? (dot.angle / (Math.PI * 2)) * SWEEP_SECONDS : 0, duration: 0.2 }}
            >
              {/* bigger invisible hit target than the mark */}
              <circle
                cx={dot.x}
                cy={dot.y}
                r={Math.max(dot.r + 6, 12)}
                fill="transparent"
                className="cursor-pointer"
                onMouseEnter={() => setHover(dot)}
                onMouseLeave={() => setHover((h) => (h === dot ? null : h))}
                onClick={() => onSelect(dot.issue)}
                data-testid="radar-dot"
              />
              <circle
                cx={dot.x}
                cy={dot.y}
                r={dot.r}
                fill={fill}
                stroke={stroke}
                strokeWidth={2}
                pointerEvents="none"
                className={hover === dot ? "opacity-100" : undefined}
              />
            </motion.g>
          );
        })}
      </svg>
      {hover ? (
        <div
          className="pointer-events-none absolute z-10 w-64 -translate-x-1/2 rounded-lg border border-rule bg-surface-raised p-3 text-sm shadow-lg"
          style={{
            left: `${((hover.x + 70) / (SIZE + 140)) * 100}%`,
            top: `calc(${((hover.y + 20) / (SIZE + 40)) * 100}% + 14px)`,
          }}
          role="tooltip"
        >
          <p className="font-semibold text-ink">{hover.issue.title}</p>
          <p className="font-mono text-[12px] text-ink-muted">
            {hover.issue.repo}#{hover.issue.number}
          </p>
          <p className="mt-1 text-ink-secondary">
            {hover.issue.availability_label}, {hover.issue.tier}, health {hover.issue.health ?? "n/a"}
          </p>
        </div>
      ) : null}
    </div>
  );
}
