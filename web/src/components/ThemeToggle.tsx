import { useEffect, useState } from "react";

export type ThemeChoice = "system" | "light" | "dark";
const KEY = "theme";
const CHOICES: ThemeChoice[] = ["system", "light", "dark"];

function readStored(): ThemeChoice {
  try {
    const value = window.localStorage.getItem(KEY);
    return value === "light" || value === "dark" ? value : "system";
  } catch {
    return "system"; // storage can be blocked; the default still works
  }
}

export function applyTheme(choice: ThemeChoice) {
  const root = document.documentElement;
  if (choice === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", choice);
}

export function ThemeToggle() {
  const [choice, setChoice] = useState<ThemeChoice>(readStored);

  useEffect(() => {
    applyTheme(choice);
    try {
      if (choice === "system") window.localStorage.removeItem(KEY);
      else window.localStorage.setItem(KEY, choice);
    } catch {
      /* not persisted; fine */
    }
  }, [choice]);

  return (
    <fieldset className="flex rounded-full border border-rule p-0.5">
      <legend className="sr-only">Colour theme</legend>
      {CHOICES.map((c) => (
        <label
          key={c}
          className={
            "cursor-pointer rounded-full px-3 py-1 text-sm has-[:focus-visible]:outline-3 has-[:focus-visible]:outline-focus " +
            (choice === c ? "bg-ink text-ground" : "text-ink-secondary hover:text-ink")
          }
        >
          <input
            type="radio"
            name="theme"
            value={c}
            checked={choice === c}
            onChange={() => setChoice(c)}
            className="sr-only"
          />
          {c.charAt(0).toUpperCase() + c.slice(1)}
        </label>
      ))}
    </fieldset>
  );
}
