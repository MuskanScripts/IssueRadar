"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { getJson, sendJson, type EmailSettings } from "@/lib/api";

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const { data, error } = useQuery({
    queryKey: ["email-settings"],
    queryFn: () => getJson<EmailSettings>("/api/v1/me/email", "your email settings"),
  });
  const save = useMutation({
    mutationFn: (body: { enabled: boolean; digest: boolean }) =>
      sendJson<EmailSettings>("/api/v1/me/email", "save", { method: "PUT", json: body }),
    // Show the new state at once; go back to the old one if saving fails.
    onMutate: (body) => {
      const before = queryClient.getQueryData<EmailSettings>(["email-settings"]);
      if (before) queryClient.setQueryData(["email-settings"], { ...before, ...body });
      return { before };
    },
    onError: (_error, _body, context) => {
      if (context?.before) queryClient.setQueryData(["email-settings"], context.before);
    },
    onSuccess: (fresh) => queryClient.setQueryData(["email-settings"], fresh),
  });

  if (error) return <p className="text-warn">{error.message}</p>;
  if (!data) return <p className="text-ink-2">Loading</p>;
  return (
    <main className="flex flex-col gap-5">
      <h1 className="text-3xl font-bold">Settings</h1>
      <section className="flex flex-col gap-3 rounded-lg border border-line bg-surface p-5">
        <h2 className="font-semibold">Email</h2>
        <p className="text-sm text-ink-2">
          {data.address
            ? `Emails go to ${data.address}, the primary email on your GitHub account.`
            : "GitHub did not share an email address, so FirstPR cannot email you."}
          {!data.sending ? " Email is not set up on this server yet, so nothing is sent for now." : ""}
        </p>
        <label className="flex items-start gap-3">
          <input
            type="checkbox"
            checked={data.enabled}
            onChange={(e) => save.mutate({ enabled: e.target.checked, digest: data.digest })}
            className="mt-1 accent-[var(--accent)]"
          />
          <span>
            <span className="block font-semibold">Send me email</span>
            <span className="text-sm text-ink-2">
              When a pull request is merged, a maintainer asks for changes, or a workspace has a
              problem. Off means no email at all.
            </span>
          </span>
        </label>
        <label className={`flex items-start gap-3 ${data.enabled ? "" : "opacity-50"}`}>
          <input
            type="checkbox"
            checked={data.digest}
            disabled={!data.enabled}
            onChange={(e) => save.mutate({ enabled: data.enabled, digest: e.target.checked })}
            className="mt-1 accent-[var(--accent)]"
          />
          <span>
            <span className="block font-semibold">Daily digest</span>
            <span className="text-sm text-ink-2">
              At 8 in the morning your time, everything else that changed. Only on days when
              something did.
            </span>
          </span>
        </label>
        {save.error ? <p className="text-sm text-warn">{save.error.message}</p> : null}
      </section>
      <section className="rounded-lg border border-line bg-surface p-5">
        <h2 className="mb-1 font-semibold">Level, skills and starter packs</h2>
        <Link href="/onboarding" className="underline">
          Change them
        </Link>
      </section>
    </main>
  );
}
