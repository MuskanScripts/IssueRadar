"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { timeAgo } from "@/components/issue-bits";
import { getJson, sendJson, type Notifications } from "@/lib/api";

export default function NotificationsPage() {
  const queryClient = useQueryClient();
  const { data, error } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => getJson<Notifications>("/api/v1/me/notifications", "notifications"),
  });
  const read = useMutation({
    mutationFn: (body: { ids?: number[]; all?: boolean }) =>
      sendJson<Notifications>("/api/v1/me/notifications/read", "mark as read", { json: body }),
    onSuccess: (fresh) => queryClient.setQueryData(["notifications"], fresh),
  });

  if (error) return <p className="text-warn">{error.message}</p>;
  if (!data) return <p className="text-ink-2">Loading</p>;
  return (
    <main className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold">Notifications</h1>
          <p className="text-ink-2">
            {data.unread ? `${data.unread} unread.` : "All read."} Email settings are in{" "}
            <Link href="/settings" className="underline">
              Settings
            </Link>
            .
          </p>
        </div>
        {data.unread ? (
          <button
            type="button"
            onClick={() => read.mutate({ all: true })}
            className="rounded-md border border-line px-4 py-2 font-semibold"
          >
            Mark all as read
          </button>
        ) : null}
      </div>
      {data.items.length === 0 ? (
        <p className="rounded-lg border border-line bg-surface p-5 text-ink-2">
          Nothing yet. You hear from FirstPR when a pull request is merged, a maintainer asks for
          changes, checks fail, or a workspace has a problem.
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {data.items.map((n) => (
            <li
              key={n.id}
              className={`flex flex-wrap items-start gap-3 rounded-lg border bg-surface p-4 ${
                n.read ? "border-line" : "border-accent/50"
              }`}
            >
              <div className="min-w-0 flex-1">
                <p className={n.read ? "" : "font-semibold"}>
                  {!n.read ? <span className="sr-only">Unread: </span> : null}
                  {n.title}
                </p>
                <p className="text-sm text-ink-2">{n.body}</p>
                <p className="text-xs text-ink-2">{timeAgo(n.created_at)}</p>
              </div>
              <div className="flex gap-2 text-sm">
                {n.link ? (
                  <Link
                    href={n.link}
                    onClick={() => !n.read && read.mutate({ ids: [n.id] })}
                    className="font-semibold text-accent underline"
                  >
                    Open
                  </Link>
                ) : null}
                {n.external_url ? (
                  <a href={n.external_url} target="_blank" rel="noreferrer" className="underline">
                    On GitHub
                  </a>
                ) : null}
                {!n.read ? (
                  <button type="button" onClick={() => read.mutate({ ids: [n.id] })} className="underline">
                    Mark read
                  </button>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
