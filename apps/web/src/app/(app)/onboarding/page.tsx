"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";
import {
  getJson,
  sendJson,
  type Level,
  type Options,
  type Profile,
  type Skill,
  type SkillKind,
  type SkillLevel,
} from "@/lib/api";

const STEPS = ["Your level", "What you know", "Starter packs"] as const;
const KIND_LABEL: Record<SkillKind, string> = {
  languages: "Languages",
  frameworks: "Frameworks",
  domains: "Areas",
};
const LEVEL_TITLE: Record<Level, string> = {
  beginner: "Beginner",
  intermediate: "Intermediate",
  pro: "Pro",
};
// Clicking a skill steps through the levels, then clears it.
const NEXT: Record<"none" | SkillLevel, SkillLevel | null> = {
  none: "learning",
  learning: "medium",
  medium: "strong",
  strong: null,
};

function browserTimeZone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

export default function OnboardingPage() {
  const options = useQuery({
    queryKey: ["onboarding-options"],
    queryFn: () => getJson<Options>("/api/v1/onboarding/options", "the choices"),
    staleTime: Infinity,
  });
  const profile = useQuery({
    queryKey: ["profile"],
    queryFn: () => getJson<Profile>("/api/v1/me/profile", "your profile"),
  });
  const error = options.error ?? profile.error;
  if (error) return <p className="text-warn">{error.message}</p>;
  if (!options.data || !profile.data) return <p className="text-ink-2">Loading</p>;
  return <Wizard options={options.data} initial={profile.data} />;
}

function Wizard({ options, initial }: { options: Options; initial: Profile }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [step, setStep] = useState(0);
  const [level, setLevel] = useState<Level>(initial.level);
  const [skills, setSkills] = useState<Skill[]>(initial.skills);
  const [packs, setPacks] = useState<string[]>(initial.packs);

  const save = useMutation({
    mutationFn: (body: Partial<Profile> & { finish: boolean }) =>
      sendJson<Profile>("/api/v1/me/profile", "save your choices", {
        method: "PUT",
        json: { timezone: browserTimeZone(), ...body },
      }),
    onSuccess: async (saved) => {
      queryClient.setQueryData(["profile"], saved);
      // A new profile means a new fit for everything.
      await queryClient.invalidateQueries({ queryKey: ["me"] });
      queryClient.removeQueries({ queryKey: ["today"] });
      queryClient.removeQueries({ queryKey: ["issues"] });
      router.push("/home");
    },
  });

  const finish = () => save.mutate({ level, skills, packs, finish: true });
  // Skipping keeps the defaults (beginner, every repo). Editing later can just leave.
  const skipAll = () => (initial.onboarded ? router.push("/home") : save.mutate({ finish: true }));

  function cycle(kind: SkillKind, name: string) {
    const current = skills.find((s) => s.kind === kind && s.name === name);
    const next = NEXT[current?.level ?? "none"];
    const rest = skills.filter((s) => !(s.kind === kind && s.name === name));
    setSkills(next ? [...rest, { kind, name, level: next }] : rest);
  }

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-6">
      <div>
        <p className="text-sm text-ink-2">
          Step {step + 1} of {STEPS.length}
        </p>
        <h1 className="text-3xl font-bold">{STEPS[step]}</h1>
        <ol className="mt-3 flex gap-2" aria-label="Progress">
          {STEPS.map((name, i) => (
            <li
              key={name}
              className={`h-1.5 flex-1 rounded-full ${i <= step ? "bg-accent" : "bg-line"}`}
              aria-current={i === step ? "step" : undefined}
            >
              <span className="sr-only">{name}</span>
            </li>
          ))}
        </ol>
      </div>

      {step === 0 ? (
        <fieldset className="grid gap-3">
          <legend className="mb-2 text-ink-2">
            We pick issues at this level for you. You can change it any time.
          </legend>
          {(Object.keys(options.levels) as Level[]).map((key) => (
            <label
              key={key}
              className={`flex cursor-pointer gap-3 rounded-lg border bg-surface p-4 ${
                level === key ? "border-accent" : "border-line"
              }`}
            >
              <input
                type="radio"
                name="level"
                value={key}
                checked={level === key}
                onChange={() => setLevel(key)}
                className="mt-1 accent-[var(--accent)]"
              />
              <span>
                <span className="block font-semibold">{LEVEL_TITLE[key]}</span>
                <span className="text-sm text-ink-2">{options.levels[key]}</span>
              </span>
            </label>
          ))}
        </fieldset>
      ) : null}

      {step === 1 ? (
        <div className="flex flex-col gap-5">
          <p className="text-ink-2">
            Click a skill to say how well you know it: once for learning, twice for medium, three
            times for strong. A fourth click clears it. Pick a few, or skip.
          </p>
          {(Object.keys(KIND_LABEL) as SkillKind[]).map((kind) => (
            <section key={kind}>
              <h2 className="mb-2 font-semibold">{KIND_LABEL[kind]}</h2>
              <ul className="flex flex-wrap gap-2">
                {options.skills[kind].map((name) => {
                  const chosen = skills.find((s) => s.kind === kind && s.name === name);
                  return (
                    <li key={name}>
                      <button
                        type="button"
                        onClick={() => cycle(kind, name)}
                        aria-pressed={Boolean(chosen)}
                        className={`rounded-full border px-3 py-1 text-sm ${
                          chosen
                            ? "border-accent bg-accent/10 font-semibold text-accent"
                            : "border-line bg-surface"
                        }`}
                      >
                        {name}
                        {chosen ? ` · ${chosen.level}` : ""}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
        </div>
      ) : null}

      {step === 2 ? (
        <fieldset className="grid gap-3">
          <legend className="mb-2 text-ink-2">
            Your daily pick comes from these repos. Choose none to get picks from all of them.
          </legend>
          {options.packs.map((pack) => (
            <label
              key={pack.key}
              className={`flex cursor-pointer gap-3 rounded-lg border bg-surface p-4 ${
                packs.includes(pack.key) ? "border-accent" : "border-line"
              }`}
            >
              <input
                type="checkbox"
                checked={packs.includes(pack.key)}
                onChange={() =>
                  setPacks((now) =>
                    now.includes(pack.key) ? now.filter((p) => p !== pack.key) : [...now, pack.key],
                  )
                }
                className="mt-1 accent-[var(--accent)]"
              />
              <span className="min-w-0">
                <span className="block font-semibold">{pack.name}</span>
                <span className="block text-sm text-ink-2">{pack.description}</span>
                <span className="mt-1 block font-mono text-xs text-ink-2">
                  {pack.repos.join(", ")}
                </span>
              </span>
            </label>
          ))}
        </fieldset>
      ) : null}

      {save.error ? <p className="text-sm text-warn">{save.error.message}</p> : null}

      <div className="flex flex-wrap items-center gap-3 border-t border-line pt-4">
        {step > 0 ? (
          <button
            type="button"
            onClick={() => setStep(step - 1)}
            className="rounded-md border border-line px-4 py-2 font-semibold"
          >
            Back
          </button>
        ) : null}
        {step < STEPS.length - 1 ? (
          <button
            type="button"
            onClick={() => setStep(step + 1)}
            className="rounded-md bg-accent px-4 py-2 font-semibold text-accent-ink hover:opacity-90"
          >
            Next
          </button>
        ) : (
          <button
            type="button"
            onClick={finish}
            disabled={save.isPending}
            className="rounded-md bg-accent px-4 py-2 font-semibold text-accent-ink hover:opacity-90 disabled:opacity-50"
          >
            {save.isPending ? "Saving" : "Show me my pick"}
          </button>
        )}
        <button
          type="button"
          onClick={skipAll}
          disabled={save.isPending}
          className="ml-auto text-sm text-ink-2 underline disabled:opacity-50"
        >
          {initial.onboarded ? "Cancel" : "Skip for now"}
        </button>
      </div>
    </main>
  );
}
