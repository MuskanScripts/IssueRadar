import * as Switch from "@radix-ui/react-switch";

import { ErrorState, Loading } from "@/components/ui/states";
import { useData, useSettingsInfo } from "@/lib/data";
import { sentence } from "@/lib/demo";
import { relativeDays } from "@/lib/utils";

export function SettingsPage() {
  const settings = useSettingsInfo();
  const { demo, setDemo } = useData();
  return (
    <div className="max-w-3xl space-y-6">
      <h1 className="font-display text-4xl font-extrabold tracking-[-0.02em]">Settings</h1>

      <section className="rounded-xl border border-rule bg-surface-raised p-5">
        <h2 className="font-display text-lg font-bold">Demo mode</h2>
        <label className="mt-3 flex items-center gap-3">
          <Switch.Root
            checked={demo}
            onCheckedChange={setDemo}
            className="relative h-6 w-11 rounded-full bg-rule data-[state=checked]:bg-action"
          >
            <Switch.Thumb className="block size-5 translate-x-0.5 rounded-full bg-surface-raised transition-transform data-[state=checked]:translate-x-[22px]" />
          </Switch.Root>
          <span>Show bundled demo data instead of your database</span>
        </label>
      </section>

      {settings.isPending ? (
        <Loading rows={3} label="Loading settings" />
      ) : settings.isError ? (
        <ErrorState error={settings.error} onRetry={() => settings.refetch()} />
      ) : (
        <>
          <section className="rounded-xl border border-rule bg-surface-raised p-5">
            <h2 className="font-display text-lg font-bold">GitHub token</h2>
            <p className="mt-2 text-ink-secondary">
              {settings.data.token_configured
                ? "A token is set. It is used only to read public data."
                : "No token is set. Create a read-only fine-grained token (docs/human-tasks.md) and set FIRSTPR_GITHUB_TOKEN."}
            </p>
          </section>
          <section className="rounded-xl border border-rule bg-surface-raised p-5">
            <h2 className="font-display text-lg font-bold">API budget</h2>
            {settings.data.last_sync ? (
              <p className="mt-2 text-ink-secondary">
                Last sync {relativeDays(settings.data.last_sync.started_at)} ({settings.data.last_sync.status}):{" "}
                {settings.data.last_sync.requests} requests, {settings.data.last_sync.not_modified} answered by cache.
              </p>
            ) : (
              <p className="mt-2 text-ink-secondary">No sync yet.</p>
            )}
            <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
              {Object.entries(settings.data.limits).map(([k, v]) => (
                <div key={k} className="contents">
                  <dt className="text-ink-secondary">{sentence(k)}</dt>
                  <dd className="font-mono">{v}</dd>
                </div>
              ))}
            </dl>
          </section>
          <section className="rounded-xl border border-rule bg-surface-raised p-5">
            <h2 className="font-display text-lg font-bold">Ranking weights</h2>
            <p className="mt-1 text-sm text-ink-muted">Change them in firstpr.yaml; docs/scoring.md explains each.</p>
            <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
              {Object.entries(settings.data.weights).map(([k, v]) => (
                <div key={k} className="contents">
                  <dt className="text-ink-secondary">{sentence(k)}</dt>
                  <dd className="font-mono">{v}</dd>
                </div>
              ))}
            </dl>
          </section>
          <section className="rounded-xl border border-rule bg-surface-raised p-5">
            <h2 className="font-display text-lg font-bold">Storage</h2>
            <p className="mt-2 font-mono text-sm break-all">{settings.data.database}</p>
          </section>
        </>
      )}
    </div>
  );
}
