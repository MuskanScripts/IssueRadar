import Link from "next/link";
import { TrackView } from "@/components/track";
import { levelLabel, publicGet, type Trending } from "@/lib/public";

export const revalidate = 300;
export const metadata = {
  title: "Trending",
  description: "Fresh open-source issues nobody has claimed, beginner picks, active repos and what was merged this week.",
};

const TABS: [string, string][] = [
  ["fresh", "Fresh"],
  ["beginner", "Good first issues"],
  ["repos", "Active repos"],
  ["merged", "Merged this week"],
];

export default async function TrendingPage({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string }>;
}) {
  const { tab: asked } = await searchParams;
  const tab = TABS.some(([key]) => key === asked) ? (asked as string) : "fresh";
  const data = await publicGet<Trending>(`/trending?tab=${tab}`, 300);
  return (
    <main className="flex flex-col gap-5 py-6">
      <TrackView event="trending_viewed" />
      <div>
        <h1 className="text-3xl font-bold">Trending</h1>
        <p className="text-ink-2">Open issues nobody has claimed yet, updated every few minutes.</p>
      </div>
      <nav aria-label="Trending lists" className="flex flex-wrap gap-2">
        {TABS.map(([key, label]) => (
          <Link
            key={key}
            href={key === "fresh" ? "/trending" : `/trending?tab=${key}`}
            aria-current={tab === key ? "page" : undefined}
            className={`rounded-full border px-3 py-1 text-sm font-semibold ${
              tab === key ? "border-accent bg-accent text-accent-ink" : "border-line bg-surface"
            }`}
          >
            {label}
          </Link>
        ))}
      </nav>
      {data === null ? <p className="text-warn">This list is not available right now.</p> : null}
      {data && (tab === "fresh" || tab === "beginner") ? (
        <ul className="flex flex-col gap-3">
          {data.issues.map((i) => (
            <li key={`${i.repo}#${i.number}`} className="flex flex-col gap-1 rounded-lg border border-line bg-surface p-4">
              <span className="font-mono text-xs text-ink-2">
                {i.repo} #{i.number}
              </span>
              <Link href={`/i/${i.repo}/${i.number}`} className="text-lg font-semibold hover:underline">
                {i.title}
              </Link>
              <span className="text-sm text-ink-2">
                {levelLabel[i.tier]} · {i.time_label}
                {i.language ? ` · ${i.language}` : ""}
                {i.health !== null ? ` · repo health ${i.health}` : ""}
              </span>
            </li>
          ))}
          {data.issues.length === 0 ? <li className="text-ink-2">Nothing here right now.</li> : null}
        </ul>
      ) : null}
      {data && tab === "repos" ? (
        <ul className="grid gap-3 md:grid-cols-2">
          {data.repos.map((r) => (
            <li key={r.repo} className="rounded-lg border border-line bg-surface p-4">
              <p className="font-mono font-semibold">{r.repo}</p>
              {r.description ? <p className="text-sm text-ink-2">{r.description}</p> : null}
              <p className="mt-1 text-sm">
                {r.free_issues} free issue{r.free_issues === 1 ? "" : "s"}
                {r.language ? ` · ${r.language}` : ""}
                {r.health !== null ? ` · health ${r.health}` : ""}
              </p>
            </li>
          ))}
        </ul>
      ) : null}
      {data && tab === "merged" ? (
        <ul className="flex flex-col gap-2">
          {data.merged.map((m) => (
            <li key={`${m.repo}#${m.number}`} className="flex flex-wrap justify-between gap-2 rounded-lg border border-line bg-surface p-3">
              <a href={m.url ?? "#"} className="hover:underline">
                <span className="font-mono text-sm text-ink-2">{m.repo}</span> {m.title}
              </a>
              <span className="text-sm text-ink-2">
                {m.handle ? <Link href={`/u/${m.handle}`} className="underline">@{m.handle}</Link> : "a FirstPR user"}
              </span>
            </li>
          ))}
          {data.merged.length === 0 ? <li className="text-ink-2">Nothing merged through FirstPR this week yet.</li> : null}
        </ul>
      ) : null}
    </main>
  );
}
