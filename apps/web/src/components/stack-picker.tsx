"use client";

import Link from "next/link";
import { useState } from "react";
import { signInUrl } from "@/lib/api";
import { levelLabel, type PublicIssue } from "@/lib/public";
import { SignInLink, track } from "./track";

const STACKS: [string, string][] = [
  ["python", "Python"],
  ["typescript", "TypeScript"],
  ["javascript", "JavaScript"],
  ["java", "Java"],
  ["go", "Go"],
  ["rust", "Rust"],
];

/** Three real beginner issues for a stack; the fourth one is for people who sign in. */
export function StackPicker({ initial }: { initial: PublicIssue[] }) {
  const [stack, setStack] = useState("python");
  const [issues, setIssues] = useState<PublicIssue[]>(initial);
  const [loading, setLoading] = useState(false);

  async function pick(next: string) {
    setStack(next);
    setLoading(true);
    track("stack_picker_used", { stack: next });
    try {
      const resp = await fetch(`/api/v1/public/issues?stack=${next}`);
      setIssues(resp.ok ? ((await resp.json()).items as PublicIssue[]) : []);
    } finally {
      setLoading(false);
    }
  }

  const shown = issues.slice(0, 3);
  return (
    <div className="flex flex-col gap-4">
      <div role="tablist" aria-label="Pick your stack" className="flex flex-wrap gap-2">
        {STACKS.map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={stack === key}
            onClick={() => pick(key)}
            className={`rounded-full border px-3 py-1 text-sm font-semibold ${
              stack === key ? "border-accent bg-accent text-accent-ink" : "border-line bg-surface"
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      <ul className={`grid gap-3 md:grid-cols-2 ${loading ? "opacity-60" : ""}`} aria-busy={loading}>
        {shown.map((issue) => (
          <li key={`${issue.repo}#${issue.number}`} className="flex flex-col gap-2 rounded-lg border border-line bg-surface p-4">
            <span className="font-mono text-xs text-ink-2">
              {issue.repo} #{issue.number}
            </span>
            <Link href={`/i/${issue.repo}/${issue.number}`} className="font-semibold hover:underline">
              {issue.title}
            </Link>
            <span className="text-sm text-ink-2">
              {levelLabel[issue.tier]} · {issue.time_label}
              {issue.health !== null ? ` · repo health ${issue.health}` : ""}
            </span>
          </li>
        ))}
        {shown.length === 0 && !loading ? (
          <li className="rounded-lg border border-line bg-surface p-4 text-sm text-ink-2 md:col-span-2">
            No free beginner issues in this stack right now. The catalogue is checked every 30
            minutes.
          </li>
        ) : null}
        <li className="flex flex-col justify-center gap-2 rounded-lg border border-dashed border-accent/50 bg-surface p-4">
          <span aria-hidden="true" className="text-2xl">🔒</span>
          <p className="font-semibold">Your own pick is waiting</p>
          <p className="text-sm text-ink-2">
            Sign in and FirstPR picks one issue a day for your level and skills, and keeps it for you
            for 48 hours.
          </p>
          <SignInLink
            href={signInUrl("/home")}
            from="stack_picker"
            className="self-start rounded-md bg-accent px-3 py-1.5 text-sm font-semibold text-accent-ink"
          >
            Sign in with GitHub
          </SignInLink>
        </li>
      </ul>
    </div>
  );
}
