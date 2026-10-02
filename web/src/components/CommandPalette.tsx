import * as Dialog from "@radix-ui/react-dialog";
import { Command } from "cmdk";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router";

import { useData, useIssues } from "@/lib/data";
import { NAV } from "@/components/nav";

/** Ctrl+K or Cmd+K: jump to a page, an issue, or flip a setting. */
export function CommandPalette({ onDensity }: { onDensity(): void }) {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const { demo, setDemo } = useData();
  const issues = useIssues();

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() === "k" && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const run = (action: () => void) => {
    setOpen(false);
    action();
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="hidden h-9 items-center gap-2 rounded-lg border border-rule bg-surface-raised px-3 text-sm text-ink-secondary hover:border-ink sm:inline-flex"
      >
        Jump to <kbd className="font-mono text-[12px]">Ctrl K</kbd>
      </button>
      <Dialog.Root open={open} onOpenChange={setOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-ink/30" />
          <Dialog.Content className="fixed top-[15vh] left-1/2 z-50 w-[min(640px,92vw)] -translate-x-1/2 overflow-hidden rounded-xl border border-rule bg-surface-raised shadow-xl">
            <Dialog.Title className="sr-only">Command palette</Dialog.Title>
            <Dialog.Description className="sr-only">Type to find a page, an issue or a setting.</Dialog.Description>
            <Command label="Command palette" className="text-ink">
              <Command.Input
                placeholder="Type a page, an issue or a setting"
                className="h-12 w-full border-b border-rule-soft bg-transparent px-4 outline-none placeholder:text-ink-muted"
              />
              <Command.List className="max-h-[50vh] overflow-y-auto p-2">
                <Command.Empty className="px-3 py-6 text-center text-ink-secondary">Nothing matches.</Command.Empty>
                <Command.Group heading="Pages" className="px-1 text-[12px] text-ink-muted">
                  {NAV.map((item) => (
                    <Command.Item
                      key={item.to}
                      value={`page ${item.label}`}
                      onSelect={() => run(() => navigate(item.to))}
                      className="cursor-pointer rounded-md px-3 py-2 text-[15px] text-ink data-[selected=true]:bg-action-tint"
                    >
                      {item.label}
                    </Command.Item>
                  ))}
                </Command.Group>
                <Command.Group heading="Settings" className="px-1 text-[12px] text-ink-muted">
                  <Command.Item
                    value="toggle demo mode"
                    onSelect={() => run(() => setDemo(!demo))}
                    className="cursor-pointer rounded-md px-3 py-2 text-[15px] text-ink data-[selected=true]:bg-action-tint"
                  >
                    {demo ? "Turn demo mode off" : "Turn demo mode on"}
                  </Command.Item>
                  <Command.Item
                    value="toggle density compact comfortable"
                    onSelect={() => run(onDensity)}
                    className="cursor-pointer rounded-md px-3 py-2 text-[15px] text-ink data-[selected=true]:bg-action-tint"
                  >
                    Switch list density
                  </Command.Item>
                </Command.Group>
                {issues.data?.length ? (
                  <Command.Group heading="Free issues" className="px-1 text-[12px] text-ink-muted">
                    {issues.data.slice(0, 50).map((issue) => (
                      <Command.Item
                        key={`${issue.repo}#${issue.number}`}
                        value={`issue ${issue.title} ${issue.repo}`}
                        onSelect={() => run(() => navigate(`/?open=${encodeURIComponent(`${issue.repo}#${issue.number}`)}`))}
                        className="cursor-pointer rounded-md px-3 py-2 text-[15px] text-ink data-[selected=true]:bg-action-tint"
                      >
                        {issue.title}
                        <span className="ml-2 font-mono text-[12px] text-ink-muted">
                          {issue.repo}#{issue.number}
                        </span>
                      </Command.Item>
                    ))}
                  </Command.Group>
                ) : null}
              </Command.List>
            </Command>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </>
  );
}
