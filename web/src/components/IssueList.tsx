import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import { useEffect, useRef, useState } from "react";

import { FreePill } from "@/components/FreePill";
import { useHotkeys } from "@/hooks/useHotkeys";
import { LevelDots } from "@/components/LevelDots";
import { sentence } from "@/lib/demo";
import { issueKey, type Issue } from "@/lib/types";
import { cn } from "@/lib/utils";

const column = createColumnHelper<Issue>();
const LEVEL_ORDER = { beginner: 0, intermediate: 1, pro: 2 } as const;

const columns = [
  column.accessor((i) => LEVEL_ORDER[i.tier], { id: "level", header: "Level" }),
  column.accessor("title", { header: "Issue" }),
  column.accessor("availability", { header: "Status" }),
  column.accessor("time_bucket", { header: "Time" }),
  column.accessor((i) => i.health ?? -1, { id: "health", header: "Health" }),
  column.accessor((i) => i.rank ?? -1, { id: "rank", header: "Rank" }),
];

/**
 * The keyboard path through the radar: every issue as a row. j/k move, o or
 * Enter opens, x dismisses, s snoozes. Virtualised so a few thousand rows stay fast.
 */
export function IssueList({
  issues,
  onOpen,
  onDismiss,
  onSnooze,
  dense,
  hotkeys,
}: {
  issues: Issue[];
  onOpen(issue: Issue): void;
  onDismiss(issue: Issue): void;
  onSnooze(issue: Issue): void;
  dense: boolean;
  hotkeys: boolean;
}) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [selected, onSelect] = useState(-1);
  // eslint-disable-next-line react-hooks/incompatible-library -- TanStack Table v8 returns fresh functions; this list is not memoized
  const table = useReactTable({
    data: issues,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });
  const rows = table.getRowModel().rows;
  const parent = useRef<HTMLDivElement>(null);
  const rowHeight = dense ? 56 : 84;
  const virtual = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parent.current,
    estimateSize: () => rowHeight,
    overscan: 8,
    initialRect: { width: 800, height: 600 },
  });

  const current = selected >= 0 ? rows[selected]?.original : undefined;
  useHotkeys(
    {
      j: () => onSelect((i) => Math.min(i + 1, rows.length - 1)),
      k: () => onSelect((i) => Math.max(i - 1, 0)),
      o: () => current && onOpen(current),
      x: () => current && onDismiss(current),
      s: () => current && onSnooze(current),
    },
    hotkeys,
  );

  useEffect(() => {
    if (selected >= 0 && selected < rows.length) {
      virtual.scrollToIndex(selected, { align: "auto" });
      document.getElementById(`issue-row-${selected}`)?.focus({ preventScroll: true });
    }
  }, [selected, rows.length, virtual]);

  return (
    <div className="rounded-xl border border-rule bg-surface-raised">
      <div className="flex flex-wrap items-center gap-2 border-b border-rule-soft px-4 py-2 text-sm text-ink-muted">
        <span>Sort by</span>
        {table.getHeaderGroups()[0]!.headers.map((header) => (
          <button
            key={header.id}
            type="button"
            onClick={header.column.getToggleSortingHandler()}
            className={cn(
              "rounded px-2 py-0.5 hover:bg-action-tint",
              header.column.getIsSorted() && "bg-action-tint font-semibold text-ink",
            )}
            aria-pressed={Boolean(header.column.getIsSorted())}
          >
            {flexRender(header.column.columnDef.header, header.getContext())}
            {header.column.getIsSorted() === "asc" ? " (low first)" : header.column.getIsSorted() === "desc" ? " (high first)" : ""}
          </button>
        ))}
      </div>
      <div ref={parent} className="max-h-[70vh] overflow-auto">
        <ol aria-label="Issues, best match first" className="relative" style={{ height: virtual.getTotalSize() }}>
          {virtual.getVirtualItems().map((item) => {
            const issue = rows[item.index]!.original;
            const active = item.index === selected;
            return (
              <li
                key={issueKey(issue)}
                className="absolute inset-x-0"
                style={{ transform: `translateY(${item.start}px)`, height: item.size }}
              >
                <button
                  id={`issue-row-${item.index}`}
                  type="button"
                  onClick={() => {
                    onSelect(item.index);
                    onOpen(issue);
                  }}
                  onFocus={() => onSelect(item.index)}
                  aria-current={active ? "true" : undefined}
                  className={cn(
                    "grid h-full w-full grid-cols-[auto_1fr_auto] items-center gap-x-4 border-b border-rule-soft px-4 text-left",
                    active ? "bg-action-tint" : "hover:bg-surface",
                  )}
                >
                  <LevelDots tier={issue.tier} />
                  <span className="min-w-0">
                    <span className="block truncate font-semibold text-ink">{issue.title}</span>
                    <span className="block truncate font-mono text-[13px] text-ink-muted">
                      {issue.repo}#{issue.number}, {issue.language ?? "unknown"}, {sentence(issue.time_bucket).toLowerCase()}, health {issue.health ?? "n/a"}
                    </span>
                    {!dense ? <span className="block truncate text-[14px] text-ink-secondary">{issue.why}</span> : null}
                  </span>
                  <FreePill availability={issue.availability} label={issue.availability_label} />
                </button>
              </li>
            );
          })}
        </ol>
      </div>
    </div>
  );
}
