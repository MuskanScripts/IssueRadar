// Calls to the FastAPI backend.
// In the browser, paths are same-origin ("/api/..."), sent on by the proxy.
// On the server, Next.js calls the API directly at API_INTERNAL_URL.

export type Health = {
  status: "ok" | "degraded";
  version: string;
  checks: Record<string, string>;
};

export const serverApiUrl = () => process.env.API_INTERNAL_URL ?? "http://localhost:8000";

export async function getHealth(base = ""): Promise<Health> {
  const resp = await fetch(`${base}/api/v1/health`, { cache: "no-store" });
  // 503 still carries a body that says which part is down.
  if (!resp.ok && resp.status !== 503) throw new Error(`Health check failed with ${resp.status}`);
  return (await resp.json()) as Health;
}
