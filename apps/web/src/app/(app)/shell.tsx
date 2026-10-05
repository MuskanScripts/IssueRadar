"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { NotificationBell } from "@/components/notification-bell";
import { AuthGate, ReconnectBanner } from "./auth-gate";

const LINKS: { href: string; label: string; soon?: boolean }[] = [
  { href: "/home", label: "Home" },
  { href: "/explore", label: "Explore" },
  { href: "/workspaces", label: "My work" },
  { href: "/pulls", label: "My PRs" },
  { href: "/leaderboard", label: "Leaderboard", soon: true },
  { href: "/paths", label: "Paths", soon: true },
];

function NavLink({ href, label, soon }: { href: string; label: string; soon?: boolean }) {
  const pathname = usePathname();
  const here = pathname === href || pathname.startsWith(`${href}/`);
  return (
    <Link
      href={href}
      aria-current={here ? "page" : undefined}
      className={`flex items-center gap-1 ${here ? "font-semibold text-ink" : "text-ink-2 hover:text-ink"}`}
    >
      {label}
      {soon ? (
        <span className="rounded-full border border-line px-1.5 text-[10px] uppercase tracking-wide">
          Soon
        </span>
      ) : null}
    </Link>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6 px-4 py-6">
      <AuthGate>
        {(me) => (
          <>
            <nav className="flex flex-wrap items-center gap-x-6 gap-y-2 border-b border-line pb-4">
              <Link href="/" className="text-lg font-bold">
                FirstPR
              </Link>
              {LINKS.map((link) => (
                <NavLink key={link.href} {...link} />
              ))}
              {me.role === "admin" ? <NavLink href="/admin" label="Admin" /> : null}
              <span className="ml-auto">
                <NotificationBell />
              </span>
              <Link
                href="/profile"
                className="flex items-center gap-2 rounded-md px-2 py-1 hover:bg-surface"
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
