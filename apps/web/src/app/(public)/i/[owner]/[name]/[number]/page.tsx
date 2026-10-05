import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { SignInLink } from "@/components/track";
import { signInUrl } from "@/lib/api";
import { levelLabel, publicGet, type IssuePreview } from "@/lib/public";

// Rendered on the first visit, then cached for an hour.
export const revalidate = 3600;

type Params = { params: Promise<{ owner: string; name: string; number: string }> };

async function load({ params }: Params) {
  const { owner, name, number } = await params;
  return publicGet<IssuePreview>(`/issues/${owner}/${name}/${number}`, 3600);
}

export async function generateMetadata(props: Params): Promise<Metadata> {
  const issue = await load(props);
  if (!issue) return { title: "Issue not found" };
  const description = `${levelLabel[issue.tier]} · ${issue.time_label} · ${issue.repo}. ${issue.why_free ?? ""}`;
  return {
    title: `${issue.title} (${issue.repo}#${issue.number})`,
    description,
    openGraph: { title: issue.title, description, type: "article" },
    twitter: { card: "summary_large_image", title: issue.title, description },
  };
}

export default async function IssuePreviewPage(props: Params) {
  const issue = await load(props);
  if (!issue) notFound();
  const free = issue.availability === "free" || issue.availability === "likely_free";
  // Start: sign in, then land on the full issue page with Start working.
  const start = signInUrl(`/issues/${issue.repo}/${issue.number}`);
  return (
    <main className="flex flex-col gap-5 py-6">
      <div className="flex flex-col gap-2">
        <span className="font-mono text-sm text-ink-2">
          {issue.repo} #{issue.number}
        </span>
        <h1 className="text-3xl font-bold">{issue.title}</h1>
        <p className="text-ink-2">
          {levelLabel[issue.tier]} · {issue.time_label}
          {issue.language ? ` · ${issue.language}` : ""} · {issue.availability_label}
        </p>
        {issue.repo_description ? <p>{issue.repo_description}</p> : null}
      </div>
      <div className="flex flex-wrap gap-3">
        {free ? (
          <SignInLink
            href={start}
            from="issue_preview"
            className="rounded-md bg-accent px-5 py-3 font-semibold text-accent-ink hover:opacity-90"
          >
            Start this issue
          </SignInLink>
        ) : (
          <p className="rounded-md border border-line px-4 py-2 text-ink-2">Not free right now.</p>
        )}
        {issue.url ? (
          <a href={issue.url} className="rounded-md border border-line px-5 py-3 font-semibold">
            View on GitHub
          </a>
        ) : null}
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <section className="rounded-lg border border-line bg-surface p-5">
          <h2 className="mb-2 font-semibold">Why we think it is free</h2>
          <p className="text-sm text-ink-2">{issue.why_free ?? "No claims, assignees or linked pull requests."}</p>
        </section>
        <section className="rounded-lg border border-line bg-surface p-5">
          <h2 className="mb-2 font-semibold">How hard it looks</h2>
          <ul className="list-disc pl-5 text-sm text-ink-2">
            {issue.difficulty_reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </section>
        <section className="rounded-lg border border-line bg-surface p-5">
          <h2 className="mb-2 font-semibold">What to do first</h2>
          <ol className="list-decimal pl-5 text-sm text-ink-2">
            {issue.checklist.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ol>
        </section>
        <section className="rounded-lg border border-line bg-surface p-5">
          <h2 className="mb-2 font-semibold">
            Repo health{issue.health !== null ? `: ${issue.health} of 100` : ""}
          </h2>
          <ul className="list-disc pl-5 text-sm text-ink-2">
            {issue.health_reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </section>
      </div>
    </main>
  );
}
