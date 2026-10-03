import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import type { ReactNode } from "react";

/** A side drawer (Radix Dialog): focus trap, Escape to close, focus returns on close. */
export function Sheet({
  open,
  onOpenChange,
  title,
  description,
  children,
}: {
  open: boolean;
  onOpenChange(open: boolean): void;
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-ink/30" />
        <Dialog.Content className="fixed inset-y-0 right-0 z-50 flex w-full max-w-xl flex-col overflow-y-auto border-l border-rule bg-surface-raised shadow-xl focus:outline-none">
          <div className="sticky top-0 flex items-start justify-between gap-4 border-b border-rule-soft bg-surface-raised px-5 py-4">
            <div className="min-w-0">
              <Dialog.Title className="font-display text-xl font-bold leading-tight">{title}</Dialog.Title>
              {description ? (
                <Dialog.Description className="mt-1 font-mono text-[13px] text-ink-muted">
                  {description}
                </Dialog.Description>
              ) : (
                <Dialog.Description className="sr-only">Details</Dialog.Description>
              )}
            </div>
            <Dialog.Close
              className="rounded-md p-1 text-ink-secondary hover:bg-action-tint hover:text-ink"
              aria-label="Close"
            >
              <X className="size-5" aria-hidden="true" />
            </Dialog.Close>
          </div>
          <div className="flex-1 px-5 py-5">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
