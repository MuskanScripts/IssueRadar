import type {
  DigestPreview,
  Insights,
  Issue,
  Meta,
  Profile,
  Pull,
  Repo,
  SavedView,
  SettingsInfo,
} from "./types";

/** Where the dashboard's data comes from: the local API, or bundled demo data. */
export interface DataSource {
  demo: boolean;
  meta(): Promise<Meta>;
  issues(all?: boolean): Promise<Issue[]>;
  repos(): Promise<Repo[]>;
  pulls(): Promise<Pull[]>;
  insights(): Promise<Insights>;
  settings(): Promise<SettingsInfo>;
  digest(): Promise<DigestPreview>;
  profile(): Promise<Profile>;
  saveProfile(profile: Profile): Promise<Profile>;
  views(): Promise<SavedView[]>;
  saveViews(views: SavedView[]): Promise<SavedView[]>;
  dismiss(issue: Issue): Promise<void>;
  snooze(issue: Issue, days: number): Promise<void>;
  feedback(issue: Issue, verdict: "harder" | "easier" | "about_right"): Promise<void>;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(
      "Can't reach the local API. Start it with `firstpr serve`, or switch on demo mode.",
      0,
    );
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* not JSON */
    }
    throw new ApiError(detail || `Request failed (${response.status})`, response.status);
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

const issuePath = (i: Issue) => `/api/issues/${i.repo}/${i.number}`;

export const httpSource: DataSource = {
  demo: false,
  meta: () => call("/api/meta"),
  issues: (all = false) => call(`/api/issues${all ? "?all=true" : ""}`),
  repos: () => call("/api/repos"),
  pulls: () => call("/api/prs"),
  insights: () => call("/api/insights"),
  settings: () => call("/api/settings"),
  digest: () => call("/api/digest"),
  profile: () => call("/api/profile"),
  saveProfile: (p) => call("/api/profile", { method: "PUT", body: JSON.stringify(p) }),
  views: () => call("/api/views"),
  saveViews: (v) => call("/api/views", { method: "PUT", body: JSON.stringify(v) }),
  dismiss: (i) => call(`${issuePath(i)}/dismiss`, { method: "POST" }),
  snooze: (i, days) => call(`${issuePath(i)}/snooze`, { method: "POST", body: JSON.stringify({ days }) }),
  feedback: (i, verdict) =>
    call(`${issuePath(i)}/feedback`, { method: "POST", body: JSON.stringify({ verdict }) }),
};
