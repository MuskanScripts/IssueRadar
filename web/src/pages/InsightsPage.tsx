import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { EmptyState, ErrorState, Loading } from "@/components/ui/states";
import { useData, useInsights } from "@/lib/data";
import { pct } from "@/lib/utils";

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="rounded-xl border border-rule bg-surface-raised p-4">
      <p className="text-sm text-ink-secondary">{label}</p>
      <p className="mt-1 font-display text-3xl font-extrabold">{value}</p>
      {note ? <p className="mt-1 text-[13px] text-ink-muted">{note}</p> : null}
    </div>
  );
}

export function InsightsPage() {
  const insights = useInsights();
  const { demo } = useData();
  return (
    <div className="space-y-5">
      <h1 className="font-display text-4xl font-extrabold tracking-[-0.02em]">Insights</h1>
      <p className="max-w-2xl text-ink-secondary">
        Your own contributions, from the pull requests you track. {demo ? "These come from demo data." : ""}
      </p>
      {insights.isPending ? (
        <Loading rows={3} label="Loading insights" />
      ) : insights.isError ? (
        <ErrorState error={insights.error} />
      ) : insights.data.opened === 0 ? (
        <EmptyState title="Nothing to count yet">
          Run <code className="font-mono">firstpr prs</code> after you open your first pull request.
        </EmptyState>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <Stat label="Pull requests opened" value={String(insights.data.opened)} />
            <Stat label="Merged" value={String(insights.data.merged)} />
            <Stat
              label="Merge rate"
              value={pct(insights.data.merge_rate)}
              note="Merged out of those merged or closed"
            />
            <Stat
              label="Median time to first review"
              value={
                insights.data.median_hours_to_first_review === null
                  ? "n/a"
                  : `${Math.round(insights.data.median_hours_to_first_review)} h`
              }
              note={insights.data.median_hours_to_first_review === null ? "No reviews yet" : undefined}
            />
          </div>
          <section aria-labelledby="per-month" className="rounded-xl border border-rule bg-surface-raised p-5">
            <h2 id="per-month" className="font-display text-lg font-bold">
              Pull requests opened per month
            </h2>
            <div className="mt-3 h-64" role="figure" aria-label="Bar chart of pull requests opened per month. The table below has the same numbers.">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={insights.data.by_month} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                  <CartesianGrid vertical={false} stroke="var(--rule-soft)" />
                  <XAxis dataKey="month" tick={{ fill: "var(--ink-muted)", fontSize: 12 }} axisLine={{ stroke: "var(--rule)" }} tickLine={false} />
                  <YAxis allowDecimals={false} tick={{ fill: "var(--ink-muted)", fontSize: 12 }} axisLine={false} tickLine={false} />
                  <Tooltip
                    cursor={{ fill: "var(--action-tint)" }}
                    contentStyle={{ background: "var(--surface-raised)", border: "1px solid var(--rule)", color: "var(--ink)" }}
                  />
                  <Bar dataKey="opened" name="Opened" fill="var(--chart-1)" radius={[4, 4, 0, 0]} maxBarSize={48} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <table className="mt-4 w-full text-sm">
              <caption className="sr-only">Pull requests opened and merged per month</caption>
              <thead>
                <tr className="text-left text-ink-secondary">
                  <th scope="col" className="py-1 font-semibold">Month</th>
                  <th scope="col" className="py-1 text-right font-semibold">Opened</th>
                  <th scope="col" className="py-1 text-right font-semibold">Merged</th>
                </tr>
              </thead>
              <tbody className="font-mono">
                {insights.data.by_month.map((row) => (
                  <tr key={row.month} className="border-t border-rule-soft">
                    <td className="py-1">{row.month}</td>
                    <td className="py-1 text-right">{row.opened}</td>
                    <td className="py-1 text-right">{row.merged}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      )}
    </div>
  );
}
