"use client";

import Link from "next/link";
import { AuthGate, ReconnectBanner } from "./auth-gate";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6 px-4 py-6">
      <AuthGate>
        {(me) => (
          <>
            <nav className="flex items-center gap-6 border-b border-line pb-4">
              <Link href="/" className="text-lg font-bold">
                FirstPR
              </Link>
              <Link href="/home" className="text-ink-2 hover:text-ink">
                Home
              </Link>
              <Link
                href="/profile"
                className="ml-auto flex items-center gap-2 rounded-md px-2 py-1 hover:bg-surface"
                aria-label="Your profile"
              >
                {me.avatar_url ? (
                  // eslint-disable-next-line @next/next/no-img-element -- small GitHub avatar
                  <img src={me.avatar_url} alt="" width={28} height={28} className="rounded-full" />
                ) : null}
                <span className="font-semibold">{me.handle}</span>
                {me.github.status !== "connected" ? (
                  <span className="h-2 w-2 rounded-full bg-warn" title="GitHub needs reconnecting" />
                ) : null}
              </Link>
            </nav>
            <ReconnectBanner me={me} />
            {children}
          </>
        )}
      </AuthGate>
    </div>
  );
}
