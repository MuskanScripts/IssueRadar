"use client";

import { useQuery } from "@tanstack/react-query";
import { getHealth } from "@/lib/api";
import { useMe } from "../auth-gate";

export default function HomePage() {
  const { data: me } = useMe();
  const { data, error, isFetching, refetch } = useQuery({
    queryKey: ["health"],
    queryFn: () => getHealth(),
    refetchInterval: 30_000,
  });

  return (
    <main className="flex flex-col gap-4">
      <h1 className="text-3xl font-bold">Welcome, {me?.name ?? me?.handle}</h1>
      <p className="text-ink-2">
        The daily pick, your pull requests and your calendar will live here, starting in Step 4.
      </p>
      <section className="rounded-lg border border-line bg-surface p-5">
        <div className="mb-2 flex items-center justify-between gap-4">
          <h2 className="font-semibold">API status</h2>
          <button
            type="button"
            onClick={() => refetch()}
            disabled={isFetching}
            className="rounded-md border border-line px-3 py-1 text-sm font-semibold disabled:opacity-50"
          >
            {isFetching ? "Checking" : "Refresh"}
          </button>
        </div>
        {error ? (
          <p className="text-sm text-warn">Could not reach the API: {error.message}</p>
        ) : data ? (
          <ul className="grid gap-1 text-sm">
            {Object.entries(data.checks).map(([name, value]) => (
              <li key={name} className="flex justify-between gap-4">
                <span className="capitalize">{name}</span>
                <span className={value === "ok" ? "text-good" : "text-warn"}>{value}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-ink-2">Checking</p>
        )}
      </section>
    </main>
  );
}
