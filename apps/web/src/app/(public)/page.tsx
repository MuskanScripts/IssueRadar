import { Suspense } from "react";
import { serverApiUrl, signInUrl, type Health } from "@/lib/api";
import { SignInNotice } from "./signin-notice";

// Rendered on the server and cached for 30 seconds, like every public page will be.
export const revalidate = 30;

async function loadHealth(): Promise<Health | null> {
  try {
    const resp = await fetch(`${serverApiUrl()}/api/v1/health`, { next: { revalidate: 30 } });
    return (await resp.json()) as Health;
  } catch {
    return null;
  }
}

export default async function IntroPage() {
  const health = await loadHealth();
  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-8 px-4 py-12">
      <header className="flex items-center justify-between gap-4">
        <span className="text-xl font-bold">FirstPR</span>
        {/* A plain link: the API answers with a redirect to GitHub. */}
        <a
          href={signInUrl("/home")}
          className="rounded-md bg-accent px-4 py-2 font-semibold text-accent-ink hover:opacity-90"
        >
          Sign in with GitHub
        </a>
      </header>

      <Suspense fallback={null}>
        <SignInNotice />
      </Suspense>

      <section className="flex flex-col gap-4">
        <h1 className="text-4xl font-bold tracking-tight text-balance sm:text-5xl">
          Your first merged pull request, picked for you today.
        </h1>
        <p className="max-w-[60ch] text-lg text-ink-2">
          FirstPR finds open-source issues nobody has claimed, at your level and in your stack,
          and stays with you until a maintainer merges your pull request.
        </p>
      </section>

      <section className="rounded-lg border border-line bg-surface p-5">
        <h2 className="mb-2 font-semibold">Platform status</h2>
        {health ? (
          <ul className="grid gap-1 text-sm">
            {Object.entries(health.checks).map(([name, value]) => (
              <li key={name} className="flex justify-between gap-4">
                <span className="capitalize">{name}</span>
                <span className={value === "ok" ? "text-good" : "text-warn"}>{value}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-warn">The API is not reachable right now.</p>
        )}
        <p className="mt-3 text-xs text-ink-2">Checked on the server, refreshed every 30 seconds.</p>
      </section>
    </main>
  );
}
