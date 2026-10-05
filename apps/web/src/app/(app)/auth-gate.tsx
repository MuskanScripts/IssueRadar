"use client";

import { useQuery } from "@tanstack/react-query";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { getMe, signInUrl, type Me } from "@/lib/api";

export function useMe() {
  return useQuery({ queryKey: ["me"], queryFn: getMe, staleTime: 60_000 });
}

// Pages that work before onboarding is finished.
const BEFORE_ONBOARDING = ["/onboarding", "/profile", "/admin"];

/** Sends signed-out visitors to GitHub sign-in, then back to this page, and new
 * people to onboarding first. */
export function AuthGate({ children }: { children: (me: Me) => React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { data: me, isPending, error } = useMe();
  const needsOnboarding =
    me != null && !me.onboarded && !BEFORE_ONBOARDING.some((p) => pathname.startsWith(p));

  useEffect(() => {
    if (!isPending && !error && me === null) window.location.assign(signInUrl(pathname));
  }, [isPending, error, me, pathname]);
  useEffect(() => {
    if (needsOnboarding) router.replace("/onboarding");
  }, [needsOnboarding, router]);

  if (error) {
    return <p className="text-warn">Could not load your account: {error.message}</p>;
  }
  if (!me || needsOnboarding) return <p className="text-ink-2">Loading</p>;
  return <>{children(me)}</>;
}

export function ReconnectBanner({ me }: { me: Me }) {
  const pathname = usePathname();
  if (me.github.status === "connected") return null;
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center gap-3 rounded-lg border border-warn/40 border-l-4 border-l-warn bg-surface p-4"
    >
      <div className="min-w-0 flex-1">
        <p className="font-semibold text-warn">Reconnect your GitHub account</p>
        <p className="text-sm text-ink-2">
          FirstPR lost access to GitHub, so your pull requests stopped updating. Your progress is
          safe. Reconnecting takes one click.
        </p>
      </div>
      <a
        href={signInUrl(pathname)}
        className="rounded-md bg-accent px-4 py-2 font-semibold text-accent-ink hover:opacity-90"
      >
        Reconnect GitHub
      </a>
    </div>
  );
}
