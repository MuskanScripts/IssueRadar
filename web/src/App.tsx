import { IssueList } from "@/components/IssueList";
import { PullRequestList } from "@/components/PullRequestList";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Wordmark } from "@/components/Wordmark";
import { brand } from "@/lib/brand";
import { demo, isRankable, type DemoDataset } from "@/lib/demo";

export function App({ data = demo }: { data?: DemoDataset }) {
  const ranked = data.issues.filter((i) => isRankable(i.availability));
  const hidden = data.issues.length - ranked.length;

  return (
    <div className="min-h-dvh bg-ground text-ink">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:rounded-md focus:bg-surface-raised focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      <header className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-4 px-4 py-5 sm:px-8">
        <Wordmark />
        <ThemeToggle />
      </header>

      <main id="main" className="mx-auto max-w-5xl px-4 pb-16 sm:px-8">
        <section aria-labelledby="radar-heading" className="pt-6">
          <div className="flex flex-wrap items-baseline justify-between gap-3">
            <h1 id="radar-heading" className="font-display text-4xl font-extrabold tracking-[-0.02em] sm:text-5xl">
              Free for you
            </h1>
            <span className="rounded-md border border-ink-muted px-2 py-0.5 font-mono text-[13px] text-ink-secondary">
              {data.label}
            </span>
          </div>
          <p className="mt-3 max-w-2xl text-ink-secondary">{data.note}</p>
          <div className="mt-6">
            <IssueList issues={ranked} repos={data.repos} />
          </div>
          <p className="mt-3 text-sm text-ink-muted">
            {hidden} claimed, in-review or not-ready issues were filtered out before ranking.
          </p>
        </section>

        <section aria-labelledby="prs-heading" className="pt-12">
          <h2 id="prs-heading" className="font-display text-2xl font-bold tracking-[-0.01em]">
            Your pull requests
          </h2>
          <div className="mt-4">
            <PullRequestList pulls={data.pull_requests} />
          </div>
        </section>
      </main>

      <footer className="border-t border-rule-soft">
        <div className="mx-auto flex max-w-5xl flex-wrap justify-between gap-2 px-4 py-5 text-sm text-ink-muted sm:px-8">
          <span>
            API budget used: <span className="font-mono">0</span> requests ({data.label.toLowerCase()}, no API calls)
          </span>
          <span>
            {brand.name} is read-only toward GitHub. Not affiliated with GitHub.
          </span>
        </div>
      </footer>
    </div>
  );
}
