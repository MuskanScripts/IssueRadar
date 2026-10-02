import { ErrorState, Loading } from "@/components/ui/states";
import { useDigest, useSettingsInfo } from "@/lib/data";
import { sentence } from "@/lib/demo";

export function DigestPage() {
  const digest = useDigest();
  const settings = useSettingsInfo();
  return (
    <div className="space-y-5">
      <h1 className="font-display text-4xl font-extrabold tracking-[-0.02em]">Digest</h1>
      <p className="max-w-2xl text-ink-secondary">
        A preview of what the next digest would contain. Send it with{" "}
        <code className="font-mono">firstpr digest --send</code>, or let the scheduled GitHub Action do it.
      </p>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <section aria-labelledby="preview" className="rounded-xl border border-rule bg-surface-raised p-5">
          <h2 id="preview" className="font-display text-lg font-bold">
            {digest.data?.title ?? "Preview"}
          </h2>
          {digest.isPending ? (
            <Loading rows={4} label="Building the preview" />
          ) : digest.isError ? (
            <ErrorState error={digest.error} />
          ) : (
            <pre className="mt-3 overflow-x-auto font-mono text-[13px] leading-relaxed whitespace-pre-wrap text-ink">
              {digest.data.markdown}
            </pre>
          )}
        </section>
        <section aria-labelledby="channels" className="rounded-xl border border-rule bg-surface p-5">
          <h2 id="channels" className="font-display text-lg font-bold">
            Channels
          </h2>
          <ul className="mt-3 space-y-2">
            {Object.entries(settings.data?.channels ?? {}).map(([name, on]) => (
              <li key={name} className="flex justify-between">
                <span>{name === "rss" ? "RSS" : sentence(name)}</span>
                <span className="text-ink-secondary">{on ? "On" : "Off"}</span>
              </li>
            ))}
          </ul>
          <p className="mt-4 text-sm text-ink-muted">
            Switch channels on in firstpr.yaml; secrets go in environment variables. See docs/digest.md.
          </p>
        </section>
      </div>
    </div>
  );
}
