import * as Switch from "@radix-ui/react-switch";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { ErrorState, Loading } from "@/components/ui/states";
import { useProfile, useSaveProfile } from "@/lib/data";
import type { Level, Profile } from "@/lib/types";

const KINDS = [
  ["languages", "Languages"],
  ["frameworks", "Frameworks"],
  ["domains", "Domains"],
] as const;
const LEVELS: Level[] = ["learning", "medium", "strong"];

export function ProfilePage() {
  const profile = useProfile();
  if (profile.isPending) return <Loading label="Loading your profile" />;
  if (profile.isError) return <ErrorState error={profile.error} />;
  return <ProfileForm initial={profile.data} />;
}

function ProfileForm({ initial }: { initial: Profile }) {
  const save = useSaveProfile();
  const [draft, setDraft] = useState<Profile>(initial);
  const [adding, setAdding] = useState({ kind: "languages" as (typeof KINDS)[number][0], name: "", level: "learning" as Level });

  const setLevel = (kind: (typeof KINDS)[number][0], name: string, level: Level | null) => {
    const next = { ...draft[kind] };
    if (level) next[name] = level;
    else delete next[name];
    setDraft({ ...draft, [kind]: next });
  };

  return (
    <div className="max-w-3xl space-y-6">
      <h1 className="font-display text-4xl font-extrabold tracking-[-0.02em]">Profile</h1>
      <p className="text-ink-secondary">
        Where you're learning you'll see Beginner issues; where you're strong, Intermediate ones. Stretch moves
        everything up one level.
      </p>

      <label className="flex items-center gap-3">
        <Switch.Root
          checked={draft.stretch}
          onCheckedChange={(on) => setDraft({ ...draft, stretch: on })}
          className="relative h-6 w-11 rounded-full bg-rule data-[state=checked]:bg-action"
        >
          <Switch.Thumb className="block size-5 translate-x-0.5 rounded-full bg-surface-raised transition-transform data-[state=checked]:translate-x-[22px]" />
        </Switch.Root>
        <span className="font-semibold">Stretch: show me one level harder</span>
      </label>

      {KINDS.map(([kind, title]) => (
        <section key={kind} className="rounded-xl border border-rule bg-surface-raised p-5">
          <h2 className="font-display text-lg font-bold">{title}</h2>
          {Object.keys(draft[kind]).length === 0 ? (
            <p className="mt-2 text-sm text-ink-muted">None yet.</p>
          ) : (
            <ul className="mt-3 space-y-2">
              {Object.entries(draft[kind]).map(([name, level]) => (
                <li key={name} className="flex flex-wrap items-center gap-3">
                  <span className="w-40 font-mono">{name}</span>
                  <label>
                    <span className="sr-only">Level in {name}</span>
                    <select
                      value={level}
                      onChange={(e) => setLevel(kind, name, e.target.value as Level)}
                      className="h-9 rounded-md border border-rule bg-surface px-2"
                    >
                      {LEVELS.map((l) => (
                        <option key={l} value={l}>
                          {l}
                        </option>
                      ))}
                    </select>
                  </label>
                  <Button size="sm" variant="ghost" onClick={() => setLevel(kind, name, null)} aria-label={`Remove ${name}`}>
                    Remove
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </section>
      ))}

      <form
        className="flex flex-wrap items-end gap-3 rounded-xl border border-rule bg-surface p-5"
        onSubmit={(e) => {
          e.preventDefault();
          if (!adding.name.trim()) return;
          setLevel(adding.kind, adding.name.trim().toLowerCase(), adding.level);
          setAdding({ ...adding, name: "" });
        }}
      >
        <label className="flex flex-col text-sm">
          Kind
          <select
            value={adding.kind}
            onChange={(e) => setAdding({ ...adding, kind: e.target.value as typeof adding.kind })}
            className="mt-1 h-10 rounded-md border border-rule bg-surface-raised px-2"
          >
            {KINDS.map(([k, t]) => (
              <option key={k} value={k}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col text-sm">
          Technology
          <input
            value={adding.name}
            onChange={(e) => setAdding({ ...adding, name: e.target.value })}
            placeholder="for example rust"
            className="mt-1 h-10 rounded-md border border-rule bg-surface-raised px-2"
          />
        </label>
        <label className="flex flex-col text-sm">
          Level
          <select
            value={adding.level}
            onChange={(e) => setAdding({ ...adding, level: e.target.value as Level })}
            className="mt-1 h-10 rounded-md border border-rule bg-surface-raised px-2"
          >
            {LEVELS.map((l) => (
              <option key={l}>{l}</option>
            ))}
          </select>
        </label>
        <Button type="submit">Add</Button>
      </form>

      <div className="flex items-center gap-3">
        <Button variant="primary" onClick={() => save.mutate(draft)} disabled={save.isPending}>
          Save profile
        </Button>
        <span role="status" className="text-sm text-ink-secondary">
          {save.isSuccess ? "Saved. Rankings now use this profile." : save.isError ? String(save.error) : ""}
        </span>
      </div>
    </div>
  );
}
