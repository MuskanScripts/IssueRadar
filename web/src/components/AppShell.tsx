import { NavLink, Outlet } from "react-router";

import { CommandPalette } from "@/components/CommandPalette";
import { NAV } from "@/components/nav";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Wordmark } from "@/components/Wordmark";
import { usePref } from "@/hooks/usePrefs";
import { brand } from "@/lib/brand";
import { useData, useSettingsInfo } from "@/lib/data";
import { cn } from "@/lib/utils";

function Budget() {
  const { demo } = useData();
  const settings = useSettingsInfo();
  if (demo) return <span>API budget used: 0 requests (demo data, no API calls)</span>;
  const last = settings.data?.last_sync;
  if (!last) return <span>API budget: no sync yet</span>;
  return (
    <span>
      API budget used in the last sync: <span className="font-mono">{last.requests}</span> requests,{" "}
      <span className="font-mono">{last.not_modified}</span> answered by cache
    </span>
  );
}

export function AppShell() {
  const { demo } = useData();
  const [density, setDensity] = usePref<"comfortable" | "compact">("density", "comfortable");
  const flipDensity = () => setDensity(density === "compact" ? "comfortable" : "compact");

  return (
    <div className="flex min-h-dvh flex-col bg-ground text-ink">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-3 focus:left-3 focus:z-50 focus:rounded-md focus:bg-surface-raised focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      <header className="border-b border-rule-soft">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3 sm:px-6">
          <Wordmark />
          {demo ? (
            <span className="rounded-md border border-ink-muted px-2 py-0.5 font-mono text-[13px] text-ink-secondary">
              Demo data
            </span>
          ) : null}
          <nav aria-label="Main" className="order-last w-full overflow-x-auto lg:order-none lg:w-auto">
            <ul className="flex gap-1">
              {NAV.map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end={item.to === "/"}
                    className={({ isActive }) =>
                      cn(
                        "block rounded-md px-3 py-1.5 text-[15px] whitespace-nowrap no-underline",
                        isActive ? "bg-ink text-ground" : "text-ink-secondary hover:bg-action-tint hover:text-ink",
                      )
                    }
                  >
                    {item.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <CommandPalette onDensity={flipDensity} />
            <button
              type="button"
              onClick={flipDensity}
              className="h-9 rounded-lg border border-rule px-3 text-sm text-ink-secondary hover:border-ink"
              aria-label={`List density: ${density}. Switch`}
            >
              {density === "compact" ? "Compact" : "Comfortable"}
            </button>
            <ThemeToggle />
          </div>
        </div>
      </header>
      <main id="main" className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-6 sm:px-6">
        <Outlet />
      </main>
      <footer className="border-t border-rule-soft">
        <div className="mx-auto flex max-w-[1400px] flex-wrap justify-between gap-2 px-4 py-4 text-sm text-ink-muted sm:px-6">
          <Budget />
          <span>{brand.name} only reads from GitHub. Not affiliated with GitHub.</span>
        </div>
      </footer>
    </div>
  );
}
