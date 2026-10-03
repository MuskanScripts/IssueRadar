import { ExternalLink } from "lucide-react";
import { useState } from "react";

import { FreePill } from "@/components/FreePill";
import { LevelDots } from "@/components/LevelDots";
import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/sheet";
import { useIssueActions } from "@/lib/data";
import { sentence } from "@/lib/demo";
import type { Issue } from "@/lib/types";

function Section({ title, items, children }: { title: string; items?: string[]; children?: React.ReactNode }) {
  return (
    <section className="mt-6">
      <h3 className="font-display text-base font-bold">{title}</h3>
      {children}
      {items && items.length ? (
        <ul className="mt-2 space-y-1.5 text-[15px] text-ink-secondary">
          {items.map((item, index) => (
            <li key={index} className="flex gap-2">
              <span aria-hidden="true" className="mt-2 size-1.5 shrink-0 rounded-full bg-ink-muted" />
              <span>{item}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

export function IssueDetail({ issue, onClose }: { issue: Issue | null; onClose(): void }) {
  const actions = useIssueActions();
  const [thanks, setThanks] = useState<string | null>(null);
  if (!issue) return null;
  const flagReasons = Array.isArray(issue.flags.reasons) ? (issue.flags.reasons as string[]) : [];

  return (
    <Sheet
      open={Boolean(issue)}
      onOpenChange={(open) => {
        if (!open) {
          setThanks(null);
          onClose();
        }
      }}
      title={issue.title}
      description={`${issue.repo}#${issue.number}`}
    >
      <div className="flex flex-wrap items-center gap-3">
        <FreePill availability={issue.availability} label={issue.availability_label} />
        <LevelDots tier={issue.tier} />
        <span className="text-sm text-ink-secondary">
          {sentence(issue.tier)}, score {issue.difficulty_score}, {sentence(issue.time_bucket).toLowerCase()}
        </span>
      </div>
      {issue.why ? <p className="mt-3 text-ink-secondary">{issue.why}</p> : null}

      <div className="mt-4 flex flex-wrap gap-2">
        {issue.url ? (
          <a
            href={issue.url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex h-10 items-center gap-2 rounded-lg bg-action px-4 text-sm font-semibold text-on-action hover:bg-action-hover hover:text-on-action"
          >
            Open on GitHub <ExternalLink className="size-4" aria-hidden="true" />
          </a>
        ) : null}
        <Button onClick={() => actions.dismiss.mutate(issue, { onSuccess: onClose })}>Dismiss</Button>
        <Button onClick={() => actions.snooze.mutate(issue, { onSuccess: onClose })}>Snooze a week</Button>
      </div>

      <Section title="Why it is free (or not)" items={issue.availability_reasons} />
      <Section title="Why this level" items={issue.difficulty_reasons} />
      <Section title={`Repo health ${issue.health ?? "not measured yet"}`} items={[...issue.health_reasons, ...flagReasons]} />
      {issue.stack_reasons.length ? <Section title="Your stack" items={issue.stack_reasons} /> : null}
      <Section title="Before you start" items={issue.checklist} />

      <Section title="Was the level right?">
        <p className="mt-1 text-sm text-ink-secondary">Your answer tunes the difficulty rules over time.</p>
        <div className="mt-2 flex flex-wrap gap-2">
          {(
            [
              ["harder", "Harder than it looked"],
              ["about_right", "About right"],
              ["easier", "Easier than it looked"],
            ] as const
          ).map(([verdict, label]) => (
            <Button
              key={verdict}
              size="sm"
              onClick={() =>
                actions.feedback.mutate({ issue, verdict }, { onSuccess: () => setThanks("Thanks, noted.") })
              }
            >
              {label}
            </Button>
          ))}
        </div>
        <p role="status" className="mt-2 text-sm text-ink-secondary">
          {thanks}
        </p>
      </Section>
    </Sheet>
  );
}
