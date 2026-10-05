// Calls to the FastAPI backend.
// In the browser, paths are same-origin ("/api/..."), sent on by the proxy.
// On the server, Next.js calls the API directly at API_INTERNAL_URL.

export type Health = {
  status: "ok" | "degraded";
  version: string;
  checks: Record<string, string>;
};

export type Me = {
  id: number;
  handle: string;
  name: string | null;
  email: string | null;
  avatar_url: string | null;
  github: { login: string; status: "connected" | "reconnect_needed" };
};

export const serverApiUrl = () => process.env.API_INTERNAL_URL ?? "http://localhost:8000";

export const signInUrl = (returnTo?: string) =>
  `/api/v1/auth/github/login${returnTo ? `?return_to=${encodeURIComponent(returnTo)}` : ""}`;

export async function getHealth(base = ""): Promise<Health> {
  const resp = await fetch(`${base}/api/v1/health`, { cache: "no-store" });
  // 503 still carries a body that says which part is down.
  if (!resp.ok && resp.status !== 503) throw new Error(`Health check failed with ${resp.status}`);
  return (await resp.json()) as Health;
}

/** The signed-in user, or null when nobody is signed in. */
export async function getMe(): Promise<Me | null> {
  const resp = await fetch("/api/v1/me", { cache: "no-store", credentials: "same-origin" });
  if (resp.status === 401) return null;
  if (!resp.ok) throw new Error(`Could not load your account (${resp.status})`);
  return (await resp.json()) as Me;
}

function csrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)firstpr_csrf=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

/** POST with the CSRF header every write needs. */
export async function post(path: string): Promise<Response> {
  return fetch(path, {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRF-Token": csrfToken() },
  });
}
