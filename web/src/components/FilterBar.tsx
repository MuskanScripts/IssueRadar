import { forwardRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { useSaveViews, useViews } from "@/lib/data";
import { sentence } from "@/lib/demo";
import { activeCount } from "@/lib/filter";
import { EMPTY_FILTERS, type Filters } from "@/lib/types";
import { cn } from "@/lib/utils";

const LEVELS = ["beginner", "intermediate", "pro"] as const;
const TIMES = ["under_an_hour", "half_a_day", "a_weekend", "a_week_or_more"];
const TYPES = ["docs", "tests", "bug", "feature", "refactor", "ci"];

function Chip({ on, onClick, children }: { on: boolean; onClick(): void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onClick}
      className={cn(
        "h-8 rounded-full border px-3 text-sm whitespace-nowrap",
        on ? "border-ink bg-ink text-ground" : "border-rule bg-surface-raised text-ink-secondary hover:border-ink",
      )}
    >
      {children}
    </button>
  );
}

function toggle<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

export const FilterBar = forwardRef<HTMLInputElement, {
  filters: Filters;
  onChange(f: Filters): void;
  languages: string[];
  shown: number;
  total: number;
}>(function FilterBar({ filters, onChange, languages, shown, total }, searchRef) {
  const views = useViews();
  const saveViews = useSaveViews();
  const [name, setName] = useState("");
  const set = (patch: Partial<Filters>) => onChange({ ...filters, ...patch });

  return (
    <div className="space-y-3 rounded-xl border border-rule bg-surface p-4">
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex min-w-[220px] flex-1 items-center gap-2">
          <span className="sr-only">Search issues</span>
          <input
            ref={searchRef}
            value={filters.q}
            onChange={(e) => set({ q: e.target.value })}
            placeholder="Search titles, repos and labels (press /)"
            className="h-10 w-full rounded-lg border border-rule bg-surface-raised px-3 text-ink placeholder:text-ink-muted"
          />
        </label>
        <span className="text-sm text-ink-muted" aria-live="polite">
          {shown} of {total} shown
        </span>
        {activeCount(filters) ? (
          <Button size="sm" variant="ghost" onClick={() => onChange(EMPTY_FILTERS)}>
            Clear filters
          </Button>
        ) : null}
      </div>
      <fieldset className="flex flex-wrap items-center gap-2">
        <legend className="mr-2 text-sm font-semibold text-ink-secondary">Level</legend>
        {LEVELS.map((l) => (
          <Chip key={l} on={filters.level.includes(l)} onClick={() => set({ level: toggle(filters.level, l) })}>
            {sentence(l)}
          </Chip>
        ))}
      </fieldset>
      <details className="group">
        <summary className="cursor-pointer text-sm font-semibold text-ink-secondary">
          More filters
          {activeCount({ ...filters, level: [], q: "" }) ? ` (${activeCount({ ...filters, level: [], q: "" })} on)` : ""}
        </summary>
        <div className="mt-3 space-y-3">
      <fieldset className="flex flex-wrap items-center gap-2">
        <legend className="mr-2 text-sm font-semibold text-ink-secondary">Time</legend>
        {TIMES.map((t) => (
          <Chip key={t} on={filters.time.includes(t)} onClick={() => set({ time: toggle(filters.time, t) })}>
            {sentence(t)}
          </Chip>
        ))}
      </fieldset>
      <fieldset className="flex flex-wrap items-center gap-2">
        <legend className="mr-2 text-sm font-semibold text-ink-secondary">Kind</legend>
        {TYPES.map((t) => (
          <Chip key={t} on={filters.type.includes(t)} onClick={() => set({ type: toggle(filters.type, t) })}>
            {t === "ci" ? "CI" : sentence(t)}
          </Chip>
        ))}
      </fieldset>
      {languages.length ? (
        <fieldset className="flex flex-wrap items-center gap-2">
          <legend className="mr-2 text-sm font-semibold text-ink-secondary">Language</legend>
          {languages.map((l) => (
            <Chip key={l} on={filters.language.includes(l)} onClick={() => set({ language: toggle(filters.language, l) })}>
              {l}
            </Chip>
          ))}
        </fieldset>
      ) : null}
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
        <label className="flex items-center gap-2">
          <span className="text-ink-secondary">Minimum repo health</span>
          <input
            type="range"
            min={0}
            max={100}
            step={10}
            value={filters.min_health ?? 0}
            onChange={(e) => set({ min_health: Number(e.target.value) || null })}
            className="accent-[var(--action)]"
          />
          <span className="w-8 font-mono">{filters.min_health ?? 0}</span>
        </label>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={filters.max_comments !== null}
            onChange={(e) => set({ max_comments: e.target.checked ? 3 : null })}
          />
          <span>Less competition (3 comments or fewer)</span>
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={filters.no_discussion} onChange={(e) => set({ no_discussion: e.target.checked })} />
          <span>Hide issues that need a proposal first</span>
        </label>
      </div>
        </div>
      </details>
      <div className="flex flex-wrap items-center gap-2 border-t border-rule-soft pt-3 text-sm">
        <span className="font-semibold text-ink-secondary">Saved views</span>
        {(views.data ?? []).map((v) => (
          <Chip key={v.name} on={false} onClick={() => onChange({ ...EMPTY_FILTERS, ...v.filters })}>
            {v.name}
          </Chip>
        ))}
        <form
          className="flex items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (!name.trim()) return;
            const rest = (views.data ?? []).filter((v) => v.name !== name.trim());
            saveViews.mutate([...rest, { name: name.trim(), filters }]);
            setName("");
          }}
        >
          <label>
            <span className="sr-only">Name for this view</span>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Name this view"
              className="h-8 w-40 rounded-md border border-rule bg-surface-raised px-2"
            />
          </label>
          <Button size="sm" type="submit" disabled={!name.trim()}>
            Save view
          </Button>
        </form>
      </div>
    </div>
  );
});
