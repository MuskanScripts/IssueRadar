"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect } from "react";
import { getJson, type Notifications } from "@/lib/api";

/** The bell in the menu. Its count stays live through the notification stream. */
export function NotificationBell() {
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => getJson<Notifications>("/api/v1/me/notifications", "notifications"),
    staleTime: 60_000,
  });

  useEffect(() => {
    // EventSource reconnects by itself when the server ends the stream.
    const source = new EventSource("/api/v1/me/notifications/stream");
    source.addEventListener("unread", (event) => {
      const unread = Number((event as MessageEvent).data);
      queryClient.setQueryData<Notifications>(["notifications"], (old) =>
        old ? { ...old, unread } : old,
      );
    });
    source.addEventListener("notification", () => {
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
      queryClient.invalidateQueries({ queryKey: ["pulls"] });
    });
    return () => source.close();
  }, [queryClient]);

  const unread = data?.unread ?? 0;
  return (
    <Link
      href="/notifications"
      className="relative rounded-md px-2 py-1 text-ink-2 hover:bg-surface hover:text-ink"
      aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}
    >
      <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
        <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
      </svg>
      {unread ? (
        <span className="absolute -right-1 -top-1 min-w-5 rounded-full bg-accent px-1 text-center text-xs font-bold text-accent-ink">
          {unread > 99 ? "99+" : unread}
        </span>
      ) : null}
    </Link>
  );
}
