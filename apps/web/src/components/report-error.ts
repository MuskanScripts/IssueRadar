"use client";

/** Sends a page error to the API, which passes it to Sentry. Never throws. */
export function reportError(error: Error & { digest?: string }) {
  try {
    void fetch("/api/v1/client-errors", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: `${error.name}: ${error.message}`.slice(0, 500),
        path: window.location.pathname.slice(0, 300),
        digest: error.digest ?? null,
      }),
      keepalive: true,
    }).catch(() => undefined);
  } catch {
    // nothing to do
  }
}
