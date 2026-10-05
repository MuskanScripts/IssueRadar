"use client";

import { useEffect } from "react";

const COOKIE = "firstpr_aid";

/** A random id for a visitor who has not signed in. Sent with the sign-in, so the
 * funnel can follow one person from the intro page to their first merge. */
function anonymousId(): string {
  const found = document.cookie.match(/(?:^|;\s*)firstpr_aid=([^;]+)/);
  if (found) return found[1];
  const id = crypto.randomUUID();
  document.cookie = `${COOKIE}=${id}; path=/; max-age=${365 * 24 * 3600}; samesite=lax`;
  return id;
}

export function track(event: string, properties: Record<string, string> = {}) {
  try {
    void fetch("/api/v1/public/events", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event, anonymous_id: anonymousId(), properties }),
      keepalive: true,
    }).catch(() => undefined);
  } catch {
    // Analytics never breaks a page.
  }
}

/** Sends one event when the page is shown. */
export function TrackView({ event }: { event: string }) {
  useEffect(() => track(event), [event]);
  return null;
}

/** A sign-in link that records the click first. A plain link: the API redirects to GitHub. */
export function SignInLink({
  href,
  className,
  children,
  from,
}: {
  href: string;
  className?: string;
  children: React.ReactNode;
  from: string;
}) {
  return (
    <a href={href} className={className} onClick={() => track("sign_in_clicked", { from })}>
      {children}
    </a>
  );
}
