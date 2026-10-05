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
  role: "user" | "admin";
  github: { login: string; status: "connected" | "reconnect_needed" };
  onboarded: boolean;
};

export type Level = "beginner" | "intermediate" | "pro";
export type SkillKind = "languages" | "frameworks" | "domains";
export type SkillLevel = "learning" | "medium" | "strong";
export type Skill = { kind: SkillKind; name: string; level: SkillLevel };

export type Options = {
  levels: Record<Level, string>;
  skill_levels: SkillLevel[];
  skills: Record<SkillKind, string[]>;
  packs: { key: string; name: string; description: string; repos: string[] }[];
};

export type Profile = {
  level: Level;
  skills: Skill[];
  packs: string[];
  timezone: string;
  onboarded: boolean;
};

export type Issue = {
  repo: string;
  number: number;
  title: string;
  url: string | null;
  labels: string[];
  language: string | null;
  tier: Level;
  time_bucket: string;
  time_label: string;
  issue_type: string;
  availability: string;
  availability_label: string;
  comments: number;
  stars: number;
  health: number | null;
  updated_at: string | null;
  changed_at: string;
  fit: number | null;
  why: string[];
  held_by_you: boolean;
};

export type IssueDetail = Issue & {
  repo_description: string | null;
  availability_reasons: string[];
  difficulty_reasons: string[];
  discussion_first: boolean;
  health_reasons: string[];
  checklist: string[];
  repo_notes: string | null;
  refreshed_at: string;
  held_until: string | null;
  live: { checked_at: string; open: boolean; assignees: string[]; comments: number; note: string | null } | null;
};

export type Today = {
  day: string;
  pick: Issue | null;
  held_until: string | null;
  swaps_left: number;
  started: boolean;
  empty_reason: string | null;
};

export type IssuePage = { items: Issue[]; next_cursor: string | null; total: number; seed: string };

export type RefreshState = {
  requested_at: string | null;
  next_allowed_at: string | null;
  data_updated_at: string | null;
};

export type Changes = {
  since: string;
  new_activity: number;
  now_taken: number;
  data_updated_at: string | null;
};

export type SyncOverview = {
  worker: string;
  issue_cards: number;
  interest: Record<string, number>;
  budgets: Record<string, { limit: number | null; remaining: number | null; paused: boolean; checked_at?: number }>;
  webhooks_last_hour: number;
  webhooks_waiting: number;
  repos: {
    full_name: string;
    token: "app" | "user";
    watchers: number;
    in_catalogue: boolean;
    status: string | null;
    note: string | null;
    open_issues: number | null;
    synced_at: string | null;
  }[];
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

/** A write (POST, PUT or DELETE) with the CSRF header every write needs. */
export async function send(
  path: string,
  { method = "POST", json }: { method?: "POST" | "PUT" | "DELETE"; json?: unknown } = {},
): Promise<Response> {
  const headers: Record<string, string> = { "X-CSRF-Token": csrfToken() };
  if (json !== undefined) headers["Content-Type"] = "application/json";
  return fetch(path, {
    method,
    credentials: "same-origin",
    headers,
    body: json === undefined ? undefined : JSON.stringify(json),
  });
}

export const post = (path: string) => send(path);

export async function getSyncOverview(): Promise<SyncOverview> {
  const resp = await fetch("/api/v1/admin/sync", { cache: "no-store", credentials: "same-origin" });
  if (resp.status === 403) throw new Error("This page is for admins.");
  if (!resp.ok) throw new Error(`Could not load the sync overview (${resp.status})`);
  return (await resp.json()) as SyncOverview;
}

/** An API error, with FastAPI's message and, for some, a code and extra fields
 * (for example `install_needed` with `install_url`). */
export class ApiError extends Error {
  status: number;
  code: string | null;
  extra: Record<string, unknown>;

  constructor(status: number, message: string, code: string | null, extra: Record<string, unknown>) {
    super(message);
    this.status = status;
    this.code = code;
    this.extra = extra;
  }
}

async function apiError(resp: Response, fallback: string): Promise<ApiError> {
  try {
    const body = await resp.json();
    const detail = body.detail;
    if (typeof detail === "string") return new ApiError(resp.status, detail, null, {});
    if (detail && typeof detail === "object" && typeof detail.message === "string") {
      const { code, message, ...extra } = detail as { code?: string; message: string };
      return new ApiError(resp.status, message, code ?? null, extra);
    }
  } catch {
    // not JSON
  }
  return new ApiError(resp.status, `${fallback} (${resp.status})`, null, {});
}

/** The error text FastAPI sent ("detail"), or a fallback with the status code. */
export async function problem(resp: Response, fallback: string): Promise<string> {
  return (await apiError(resp, fallback)).message;
}

/** A signed-in GET. Throws an ApiError with the API's own message when it fails. */
export async function getJson<T>(path: string, what: string): Promise<T> {
  const resp = await fetch(path, { cache: "no-store", credentials: "same-origin" });
  if (!resp.ok) throw await apiError(resp, `Could not load ${what}`);
  return (await resp.json()) as T;
}

/** A write that returns JSON. Throws an ApiError with the API's own message when it fails. */
export async function sendJson<T>(
  path: string,
  what: string,
  options: { method?: "POST" | "PUT" | "DELETE"; json?: unknown } = {},
): Promise<T> {
  const resp = await send(path, options);
  if (!resp.ok) throw await apiError(resp, `Could not ${what}`);
  return (await resp.json()) as T;
}

export const issuePath = (issue: { repo: string; number: number }) =>
  `/issues/${issue.repo}/${issue.number}`;

/** Logs what people do with a recommendation. Never blocks or fails the page. */
export function logEvent(
  issue: { repo: string; number: number },
  surface: "daily" | "explore" | "issue",
  action: "opened" | "github",
) {
  void send("/api/v1/me/events", {
    json: { repo: issue.repo, number: issue.number, surface, action },
  }).catch(() => undefined);
}

export type WorkspaceStep = {
  key: string;
  label: string;
  state: "pending" | "running" | "done" | "failed" | "skipped";
  detail: string;
};

export type Workspace = {
  id: number;
  repo: string;
  number: number;
  issue_title: string;
  issue_url: string | null;
  practice: boolean;
  mode: "codespace" | "local";
  status: "queued" | "working" | "ready" | "failed" | "pr_open" | "closed";
  steps: WorkspaceStep[];
  note: string | null;
  help_url: string | null;
  fork: string | null;
  branch: string | null;
  base_branch: string | null;
  clone_url: string | null;
  codespace: { name: string; url: string | null; state: string | null } | null;
  pull_request: { number: number | null; url: string; state: string | null } | null;
  created_at: string;
  updated_at: string;
};

export type WorkspaceList = {
  items: Workspace[];
  practice_repo: string | null;
  practice_done: boolean;
  open_prs: number;
  open_pr_limit: number;
};

export type WorkChanges = {
  ahead_by: number;
  commits: { sha: string; message: string }[];
  files: { filename: string; status: string; additions: number; deletions: number }[];
  compare_url: string | null;
  pull_request: Workspace["pull_request"];
};

export type PullDraft = { title: string; body: string; base: string; head: string; from_template: boolean };

export type PullResult = { opened: boolean; manual_url: string | null; workspace: Workspace };

export const workspacePath = (ws: { id: number }) => `/workspaces/${ws.id}`;

export type Pull = {
  repo: string;
  number: number;
  title: string;
  url: string | null;
  status: string;
  status_label: string;
  needs_you: boolean;
  what_to_do: string;
  reasons: string[];
  nudge: string | null;
  days_quiet: number;
  draft: boolean;
  opened_at: string | null;
  closed_at: string | null;
  timeline: { at: string; text: string }[];
  checked_at: string;
};

export type Pulls = { items: Pull[]; checked_at: string | null; next_refresh_at: string | null };

export type NotificationItem = {
  id: number;
  kind: string;
  title: string;
  body: string;
  link: string | null;
  external_url: string | null;
  created_at: string;
  read: boolean;
};

export type Notifications = { items: NotificationItem[]; unread: number };

export type EmailSettings = { address: string | null; enabled: boolean; digest: boolean; sending: boolean };
