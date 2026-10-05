"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { post } from "@/lib/api";
import { useMe } from "../auth-gate";

export default function ProfilePage() {
  const { data: me } = useMe();
  const queryClient = useQueryClient();
  const router = useRouter();
  const [signingOut, setSigningOut] = useState(false);
  const [problem, setProblem] = useState("");

  async function signOut() {
    setSigningOut(true);
    const resp = await post("/api/v1/auth/logout");
    if (resp.ok) {
      queryClient.clear();
      router.replace("/");
      return;
    }
    setSigningOut(false);
    setProblem("Signing out did not work. Refresh the page and try again.");
  }

  if (!me) return null;
  return (
    <main className="flex flex-col gap-6">
      <section className="flex flex-wrap items-center gap-4 rounded-lg border border-line bg-surface p-5">
        {me.avatar_url ? (
          // eslint-disable-next-line @next/next/no-img-element -- small GitHub avatar
          <img src={me.avatar_url} alt="" width={72} height={72} className="rounded-full" />
        ) : null}
        <div className="min-w-0">
          <h1 className="text-3xl font-bold">{me.name ?? me.handle}</h1>
          <p className="font-mono text-sm text-ink-2">@{me.handle}</p>
        </div>
      </section>

      <section className="rounded-lg border border-line bg-surface p-5">
        <h2 className="mb-3 font-semibold">Connected GitHub account</h2>
        <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
          <dt className="text-ink-2">Account</dt>
          <dd className="font-mono">@{me.github.login}</dd>
          <dt className="text-ink-2">Status</dt>
          <dd className={me.github.status === "connected" ? "text-good" : "text-warn"}>
            {me.github.status === "connected" ? "Connected" : "Reconnect needed"}
          </dd>
          <dt className="text-ink-2">Email</dt>
          <dd>{me.email ?? "Not shared"}</dd>
        </dl>
      </section>

      <section className="rounded-lg border border-line bg-surface p-5">
        <h2 className="mb-1 font-semibold">Settings</h2>
        <p className="mb-3 text-sm text-ink-2">
          Email, your level, skills and starter packs.
        </p>
        <Link href="/settings" className="rounded-md border border-line px-4 py-2 font-semibold">
          Open Settings
        </Link>
      </section>

      <section className="rounded-lg border border-line bg-surface p-5">
        <h2 className="mb-3 font-semibold">Account</h2>
        <button
          type="button"
          onClick={signOut}
          disabled={signingOut}
          className="rounded-md border border-line px-4 py-2 font-semibold disabled:opacity-50"
        >
          {signingOut ? "Signing out" : "Sign out"}
        </button>
        {problem ? <p className="mt-2 text-sm text-warn">{problem}</p> : null}
      </section>
    </main>
  );
}
