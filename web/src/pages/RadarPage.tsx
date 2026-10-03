import { useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router";

import { FilterBar } from "@/components/FilterBar";
import { IssueDetail } from "@/components/IssueDetail";
import { IssueList } from "@/components/IssueList";
import { Radar } from "@/components/Radar";
import { EmptyState, ErrorState, Loading } from "@/components/ui/states";
import { useHotkeys } from "@/hooks/useHotkeys";
import { usePref } from "@/hooks/usePrefs";
import { useData, useIssueActions, useIssues } from "@/lib/data";
import { applyFilters, languagesOf } from "@/lib/filter";
import { EMPTY_FILTERS, issueKey, type Filters, type Issue } from "@/lib/types";

export function RadarPage() {
  const { demo, setDemo } = useData();
  const [showAll, setShowAll] = useState(false);
  const issues = useIssues(showAll);
  const actions = useIssueActions();
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [open, setOpen] = useState<Issue | null>(null);
  const [density] = usePref<"comfortable" | "compact">("density", "comfortable");
  const search = useRef<HTMLInputElement>(null);

  const all = useMemo(() => issues.data ?? [], [issues.data]);
  const shown = useMemo(() => applyFilters(all, filters), [all, filters]);

  // The command palette links here with ?open=owner/repo#12.
  const [params, setParams] = useSearchParams();
  const linked = params.get("open");
  useHotkeys({ "/": () => search.current?.focus() }, !open && !linked);
  const current = open ?? (linked ? (all.find((i) => issueKey(i) === linked) ?? null) : null);
  const close = () => {
    setOpen(null);
    if (linked) {
      params.delete("open");
      setParams(params, { replace: true });
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-4xl font-extrabold tracking-[-0.02em]">Radar</h1>
          <p className="mt-1 max-w-2xl text-ink-secondary">
            Inner ring Beginner, outer ring Pro. Bigger dots are healthier repos. Amber means free.
          </p>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} />
          <span>Also show issues that aren't free</span>
        </label>
      </div>

      <FilterBar
        ref={search}
        filters={filters}
        onChange={setFilters}
        languages={languagesOf(all)}
        shown={shown.length}
        total={all.length}
      />

      {issues.isPending ? (
        <Loading label="Loading issues" />
      ) : issues.isError ? (
        <div className="space-y-3">
          <ErrorState error={issues.error} onRetry={() => issues.refetch()} />
          {!demo ? (
            <button type="button" className="text-sm font-semibold text-action underline" onClick={() => setDemo(true)}>
              Switch on demo mode instead
            </button>
          ) : null}
        </div>
      ) : all.length === 0 ? (
        <EmptyState title="No free issues yet">
          Watch a few repositories with <code className="font-mono">firstpr watch add owner/repo</code> or{" "}
          <code className="font-mono">firstpr pack add ai-agents-and-mcp</code>, then run{" "}
          <code className="font-mono">firstpr sync</code>.
        </EmptyState>
      ) : shown.length === 0 ? (
        <EmptyState title="Nothing matches these filters">Clear a filter or two to see more.</EmptyState>
      ) : (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
          <Radar issues={shown} onSelect={setOpen} />
          <div>
            <p className="mb-2 text-sm text-ink-muted">
              Keys: j and k move, o opens, x dismisses, s snoozes, / searches.
            </p>
            <IssueList
              issues={shown}
              onOpen={setOpen}
              onDismiss={(i) => actions.dismiss.mutate(i)}
              onSnooze={(i) => actions.snooze.mutate(i)}
              dense={density === "compact"}
              hotkeys={!current}
            />
          </div>
        </div>
      )}
      <IssueDetail issue={current} onClose={close} />
    </div>
  );
}
