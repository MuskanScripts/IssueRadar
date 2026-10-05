import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ActivityCalendar } from "@/components/activity-calendar";
import { publicGet, type PublicProfile } from "@/lib/public";

export const revalidate = 3600;

type Params = { params: Promise<{ handle: string }> };

async function load({ params }: Params) {
  const { handle } = await params;
  return publicGet<PublicProfile>(`/profiles/${handle}`, 3600);
}

export async function generateMetadata(props: Params): Promise<Metadata> {
  const p = await load(props);
  if (!p) return { title: "Profile not found", robots: { index: false } };
  const name = p.name ?? p.handle;
  const description = `${p.merged} merged pull request${p.merged === 1 ? "" : "s"} in ${p.repos} open-source repo${p.repos === 1 ? "" : "s"}, ${p.xp} XP, best streak ${p.best_streak} days.`;
  return {
    title: `${name} (@${p.handle})`,
    description,
    openGraph: { title: `${name} on FirstPR`, description, type: "profile" },
    twitter: { card: "summary_large_image", title: `${name} on FirstPR`, description },
  };
}

export default async function PublicProfilePage(props: Params) {
  const p = await load(props);
  if (!p) notFound();
  const today = p.calendar[p.calendar.length - 1]?.day ?? "";
  const days = p.calendar.map((d) => ({
    day: d.day,
    minutes: d.minutes,
    web_minutes: d.minutes,
    codespace_minutes: 0,
    commits: 0,
    green: d.green,
    frozen: false,
  }));
  return (
    <main className="flex flex-col gap-6 py-6">
      <section className="flex flex-wrap items-center gap-4">
        {p.avatar_url ? (
          // eslint-disable-next-line @next/next/no-img-element -- small GitHub avatar
          <img src={p.avatar_url} alt="" width={80} height={80} className="rounded-full" />
        ) : null}
        <div>
          <h1 className="text-3xl font-bold">{p.name ?? p.handle}</h1>
          <p className="font-mono text-ink-2">@{p.handle}</p>
        </div>
      </section>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {(
          [
            ["Merged pull requests", p.merged],
            ["Repos", p.repos],
            ["XP", p.xp],
            ["Best streak", p.best_streak],
          ] as const
        ).map(([label, value]) => (
          <div key={label} className="rounded-lg border border-line bg-surface p-4">
            <p className="text-2xl font-bold">{value}</p>
            <p className="text-sm text-ink-2">{label}</p>
          </div>
        ))}
      </div>
      <section className="rounded-lg border border-line bg-surface p-5">
        <h2 className="mb-2 font-semibold">Activity</h2>
        <ActivityCalendar days={days} today={today} />
      </section>
      {p.badges.length ? (
        <section>
          <h2 className="mb-2 font-semibold">Badges</h2>
          <ul className="flex flex-wrap gap-2">
            {p.badges.map((b) => (
              <li key={b} className="rounded-full border border-accent/50 px-3 py-1 text-sm">
                ★ {b}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      <section className="rounded-lg border border-line bg-surface p-5">
        <h2 className="mb-2 font-semibold">Merged pull requests</h2>
        {p.merged_pulls.length ? (
          <ul className="flex flex-col gap-1 text-sm">
            {p.merged_pulls.map((m) => (
              <li key={`${m.repo}#${m.number}`}>
                <a href={m.url ?? "#"} className="hover:underline">
                  <span className="font-mono text-ink-2">{m.repo}</span> {m.title}
                </a>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-ink-2">None yet.</p>
        )}
      </section>
      {p.skills.length ? (
        <p className="text-sm text-ink-2">Skills: {p.skills.join(", ")}</p>
      ) : null}
    </main>
  );
}
