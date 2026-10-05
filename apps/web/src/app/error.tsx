"use client";

import { useEffect } from "react";
import { reportError } from "@/components/report-error";

export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => reportError(error), [error]);
  return (
    <main className="mx-auto flex max-w-xl flex-col gap-4 px-4 py-16">
      <h1 className="text-3xl font-bold">Something went wrong</h1>
      <p className="text-ink-2">The problem was reported. Try again, or come back in a minute.</p>
      <div className="flex gap-3">
        <button type="button" onClick={reset} className="rounded-md bg-accent px-4 py-2 font-semibold text-accent-ink">
          Try again
        </button>
        <a href="/feedback" className="rounded-md border border-line px-4 py-2 font-semibold">
          Tell us what happened
        </a>
      </div>
    </main>
  );
}
