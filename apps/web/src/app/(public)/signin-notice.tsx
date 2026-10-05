"use client";

import { useSearchParams } from "next/navigation";

const MESSAGES: Record<string, string> = {
  cancelled: "Sign-in was cancelled on GitHub. You can try again any time.",
  expired: "That sign-in link expired or was already used. Please sign in again.",
  failed: "GitHub did not accept the sign-in. Please try again.",
  deleted: "Your account and everything FirstPR stored about you are deleted.",
  invite:
    "FirstPR is open to invited testers for now. Ask for an invite with the Feedback link below, and we will let you know when it opens to everyone.",
};

export function SignInNotice() {
  const reason = useSearchParams().get("signin");
  const message = reason ? MESSAGES[reason] : undefined;
  if (!message) return null;
  return (
    <p role="status" className="rounded-md border border-warn/40 bg-surface px-4 py-3 text-sm text-warn">
      {message}
    </p>
  );
}
