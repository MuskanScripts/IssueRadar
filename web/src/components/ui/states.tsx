import { AlertTriangle } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden="true" className={cn("animate-pulse rounded-md bg-rule-soft", className)} />;
}

export function Loading({ rows = 5, label = "Loading" }: { rows?: number; label?: string }) {
  return (
    <div role="status" aria-label={label} className="space-y-3">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-14 w-full" />
      ))}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-rule bg-surface p-8 text-center">
      <p className="font-display text-lg font-bold">{title}</p>
      <div className="mx-auto mt-2 max-w-md text-ink-secondary">{children}</div>
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    <div role="alert" className="rounded-xl border border-rule bg-surface p-6">
      <p className="flex items-center gap-2 font-semibold">
        <AlertTriangle className="size-5" aria-hidden="true" /> Something went wrong
      </p>
      <p className="mt-2 text-ink-secondary">{message}</p>
      {onRetry ? (
        <button type="button" onClick={onRetry} className="mt-3 text-sm font-semibold text-action underline">
          Try again
        </button>
      ) : null}
    </div>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="rounded border border-rule bg-surface px-1.5 py-0.5 font-mono text-[12px] text-ink-secondary">
      {children}
    </kbd>
  );
}

export function Pill({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span className={cn("inline-flex items-center rounded-md bg-action-tint px-2 py-0.5 text-sm font-medium text-ink", className)}>
      {children}
    </span>
  );
}
