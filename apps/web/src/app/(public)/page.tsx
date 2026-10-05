import Link from "next/link";
import { connection } from "next/server";
import { Suspense } from "react";
import { StackPicker } from "@/components/stack-picker";
import { SignInLink, TrackView } from "@/components/track";
import { signInUrl } from "@/lib/api";
import { publicGet, type IssueList, type PublicStats, type Trending } from "@/lib/public";
import { SignInNotice } from "./signin-notice";

// Rendered for each visit, from data cached for 5 minutes (here and in the API), so
// the numbers are never the empty ones from build time.

const TILES: [string, string][] = [
  ["Free issues only", "Every issue is checked for assignees, linked pull requests and claims in the comments before you see it."],
  ["At your level", "Beginner, intermediate or pro, from the labels, the size of the change and the repo's own rules."],
  ["Repos that answer", "A health score from how fast maintainers reply and merge, so your work does not sit for months."],
  ["One pick a day", "One issue picked for you and held for 48 hours, so nobody else is sent to it."],
  ["Ready to code in a click", "A fork, a branch and a Codespace set up for you. Nothing is posted without your click."],
  ["With you until it is merged", "Your pull requests in one place, what needs you first, and an email when it is merged."],
];

const QUESTIONS: [string, string][] = [
  ["Is it free?", "Yes. FirstPR is open source (MIT). You only need a GitHub account."],
  ["What can FirstPR do with my GitHub account?", "Read public data, and fork, branch, open a Codespace or a pull request only when you click the button for it. It never comments or posts for you, and private repos are never read."],
  ["I have never contributed to open source. Is this for me?", "That is who it is for. Pick the beginner level, and your first pull request goes to a practice repo before a real project."],
  ["Which projects are in it?", "Starter packs of well-kept repos in Python, TypeScript, Java and more, checked for how often they merge outside pull requests. You can add your own."],
];

export const metadata = {
  title: { absolute: "FirstPR: your first merged pull request, picked for you" },
  description:
    "Open-source issues nobody has claimed, at your level and in your stack, and help all the way to a merged pull request.",
};

function Number({ value, label }: { value: number | undefined; label: string }) {
  return (
    <div className="rounded-lg border border-line bg-surface p-4">
      <p className="text-3xl font-bold">{value ?? "–"}</p>
      <p className="text-sm text-ink-2">{label}</p>
    </div>
  );
}

export default async function IntroPage() {
  await connection();
  const [stats, picks, merged] = await Promise.all([
    publicGet<PublicStats>("/stats", 300),
    publicGet<IssueList>("/issues?stack=python", 300),
    publicGet<Trending>("/trending?tab=merged", 300),
  ]);
  return (
    <main className="flex flex-col gap-12 py-6">
      <TrackView event="intro_viewed" />
      <Suspense fallback={null}>
        <SignInNotice />
      </Suspense>

      <section className="flex flex-col gap-5">
        <h1 className="max-w-[20ch] text-4xl font-bold tracking-tight text-balance sm:text-5xl">
          Your first merged pull request, picked for you today.
        </h1>
        <p className="max-w-[60ch] text-lg text-ink-2">
          FirstPR finds open-source issues nobody has claimed, at your level and in your stack, and
          stays with you until a maintainer merges your pull request.
        </p>
        <div className="flex flex-wrap gap-3">
          <SignInLink
            href={signInUrl("/home")}
            from="hero"
            className="rounded-md bg-accent px-5 py-3 font-semibold text-accent-ink hover:opacity-90"
          >
            Get my first pick
          </SignInLink>
          <Link href="/trending" className="rounded-md border border-line px-5 py-3 font-semibold">
            See what is trending
          </Link>
        </div>
      </section>

      <section aria-label="FirstPR in numbers" className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Number value={stats?.free_issues} label="free issues right now" />
        <Number value={stats?.repos} label="repos checked every 30 minutes" />
        <Number value={stats?.merged_this_week} label="pull requests merged this week" />
        <Number value={stats?.people} label="people using FirstPR" />
      </section>

      <section className="flex flex-col gap-4">
        <h2 className="text-2xl font-bold">Pick your stack</h2>
        <StackPicker initial={picks?.items ?? []} />
      </section>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {TILES.map(([title, text]) => (
          <div key={title} className="rounded-lg border border-line bg-surface p-5">
            <h3 className="mb-1 font-semibold">{title}</h3>
            <p className="text-sm text-ink-2">{text}</p>
          </div>
        ))}
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-2xl font-bold">Merged this week</h2>
        {merged?.merged.length ? (
          <ul className="flex flex-col gap-2">
            {merged.merged.slice(0, 6).map((m) => (
              <li key={`${m.repo}#${m.number}`} className="flex flex-wrap justify-between gap-2 rounded-lg border border-line bg-surface p-3 text-sm">
                <a href={m.url ?? "#"} className="hover:underline">
                  <span className="font-mono text-ink-2">{m.repo}</span> {m.title}
                </a>
                <span className="text-ink-2">
                  {m.handle ? <Link href={`/u/${m.handle}`} className="underline">@{m.handle}</Link> : "a FirstPR user"}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-ink-2">Nothing yet this week. Yours could be the first.</p>
        )}
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-2xl font-bold">Questions</h2>
        {QUESTIONS.map(([q, a]) => (
          <details key={q} className="rounded-lg border border-line bg-surface p-4">
            <summary className="cursor-pointer font-semibold">{q}</summary>
            <p className="mt-2 text-ink-2">{a}</p>
          </details>
        ))}
      </section>
    </main>
  );
}
