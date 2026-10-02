// Demo mode: the same screens, fed from the bundled demo fixtures (ADR 0008).
// Nothing here is real data, and the UI labels it "Demo data" everywhere.

import { demo, isRankable, sentence } from "./demo";
import type { DataSource } from "./source";
import type { Insights, Issue, Profile, Pull, Repo, SavedView, Tier } from "./types";

const STORE = "demo-state";

interface DemoState {
  hidden: string[];
  profile?: Profile;
  views?: SavedView[];
}

function load(): DemoState {
  try {
    const saved = JSON.parse(localStorage.getItem(STORE) ?? "{}") as Partial<DemoState>;
    return { ...saved, hidden: saved.hidden ?? [] };
  } catch {
    return { hidden: [] };
  }
}

function store(state: DemoState) {
  try {
    localStorage.setItem(STORE, JSON.stringify(state));
  } catch {
    /* fine: demo state just won't persist */
  }
}

const DEMO_PROFILE: Profile = {
  stretch: false,
  languages: { python: "learning", java: "strong", typescript: "medium" },
  frameworks: {},
  domains: { "agents-and-mcp": "medium" },
  prefer_issue_types: ["docs", "tests"],
};

const LABELS: Record<string, string> = {
  free: "Free",
  likely_free: "Likely free",
  claimed: "Claimed",
  has_pr: "Has a PR",
  not_ready: "Not ready",
  unclear: "Unclear",
};

function toIssue(i: (typeof demo.issues)[number], rank: number | null): Issue {
  const repo = demo.repos.find((r) => r.full_name === i.repo)!;
  const flags = repo.health.reasons.some((r) => r.includes("DCO"))
    ? { dco: true, reasons: ["Requires DCO sign-off: commits need Signed-off-by"] }
    : { reasons: [] };
  return {
    repo: i.repo,
    number: i.number,
    title: i.title,
    url: null,
    labels: i.labels,
    language: i.language,
    stars: repo.stars,
    comments: i.comments,
    updated_at: i.updated_at,
    availability: i.availability,
    availability_label: LABELS[i.availability] ?? sentence(i.availability),
    availability_reasons: i.why_available,
    tier: i.tier as Tier,
    difficulty_score: i.difficulty_score,
    time_bucket: i.time_bucket,
    issue_type: i.issue_type,
    difficulty_reasons: i.why_tier,
    discussion_first: i.why_tier.some((r) => r.toLowerCase().includes("proposal")),
    health: repo.health.score,
    health_reasons: repo.health.reasons,
    flags,
    stack_fit: 0.5,
    stack_reasons: [],
    rank,
    rank_parts: {},
    why: i.why_here,
    frameworks: [],
    domains: [i.domain],
    checklist: [
      `Read ${i.repo}'s CONTRIBUTING guide before writing code.`,
      "Say on the issue that you'd like to work on it, the way this repo expects.",
      "One issue per pull request.",
      "Include a test that fails before your change and passes after.",
      "Keep the diff small and focused.",
    ],
  };
}

function issues(all: boolean): Issue[] {
  const hidden = new Set(load().hidden);
  const ranked = demo.issues.filter((i) => isRankable(i.availability));
  return demo.issues
    .filter((i) => all || isRankable(i.availability))
    .filter((i) => !hidden.has(`${i.repo}#${i.number}`))
    .map((i) => {
      const position = ranked.indexOf(i);
      return toIssue(i, position >= 0 ? Math.round((1 - position / ranked.length) * 100) / 100 : null);
    });
}

const pulls: Pull[] = demo.pull_requests.map((p) => ({
  repo: p.repo,
  number: p.number,
  title: p.title,
  url: null,
  status: p.status,
  status_label: sentence(p.status),
  needs_you: p.needs_you,
  reasons: [p.needs_you],
  nudge:
    p.status === "stale"
      ? "Hi! Just checking in on this when you have a moment. I'm happy to change anything, and thanks for maintaining the project."
      : null,
  draft: false,
  days_quiet: 0,
  opened_at: p.opened_at,
  closed_at: p.status === "merged" ? p.last_activity_at : null,
  timeline: [
    { at: p.opened_at, actor: "you", kind: "opened", text: "You opened it" },
    { at: p.last_activity_at, actor: null, kind: "activity", text: "Last activity" },
  ],
}));

function insights(): Insights {
  const merged = pulls.filter((p) => p.status === "merged").length;
  const byMonth = new Map<string, { month: string; opened: number; merged: number }>();
  for (const p of pulls) {
    const month = (p.opened_at ?? "").slice(0, 7);
    const row = byMonth.get(month) ?? { month, opened: 0, merged: 0 };
    row.opened += 1;
    row.merged += p.status === "merged" ? 1 : 0;
    byMonth.set(month, row);
  }
  return {
    opened: pulls.length,
    merged,
    closed_unmerged: 0,
    open_now: pulls.length - merged,
    merge_rate: merged ? 1 : null,
    median_hours_to_first_review: null,
    by_month: [...byMonth.values()].sort((a, b) => a.month.localeCompare(b.month)),
  };
}

const repos: Repo[] = demo.repos.map((r) => ({
  full_name: r.full_name,
  description: r.description,
  language: r.language,
  stars: r.stars,
  archived: false,
  health: r.health.score,
  health_parts: {},
  health_reasons: r.health.reasons,
  open_issues: demo.issues.filter((i) => i.repo === r.full_name).length,
  free_issues: demo.issues.filter((i) => i.repo === r.full_name && isRankable(i.availability)).length,
  last_synced_at: demo.as_of,
  pushed_at: null,
  sync_error: null,
}));

export const demoSource: DataSource = {
  demo: true,
  meta: async () => ({
    name: "Demo",
    version: "demo",
    tagline: demo.note,
    demo: true,
    token_configured: false,
  }),
  issues: async (all = false) => issues(all),
  repos: async () => repos,
  pulls: async () => pulls,
  insights: async () => insights(),
  settings: async () => ({
    token_configured: false,
    database: "none (demo)",
    last_sync: null,
    channels: { markdown: true, rss: true, email: false, telegram: false, discord: false, slack: false },
    limits: { rest_per_hour: 5000, graphql_points_per_hour: 5000, search_per_minute: 30, safety_margin: 0.1 },
    weights: { tier_fit: 0.35, repo_health: 0.25, stack_fit: 0.2, freshness: 0.1, low_competition: 0.1 },
  }),
  digest: async () => {
    const free = issues(false).slice(0, 5);
    const markdown = [
      `# ${demo.label}: ${free.length} free issues for you`,
      "",
      "## Free for you",
      "",
      ...free.map((i) => `- **${i.repo}#${i.number}** ${i.title}. ${i.availability_label}. ${i.why}`),
      "",
      "## Your pull requests",
      "",
      ...pulls.map((p) => `- **${p.repo}#${p.number}** ${p.title}. ${p.status_label}. ${p.needs_you}`),
    ].join("\n");
    return { title: `${free.length} free issues for you`, markdown, html: "", items: free.length + pulls.length };
  },
  profile: async () => load().profile ?? DEMO_PROFILE,
  saveProfile: async (profile) => {
    store({ ...load(), profile });
    return profile;
  },
  views: async () => load().views ?? [],
  saveViews: async (views) => {
    store({ ...load(), views });
    return views;
  },
  dismiss: async (issue) => {
    const state = load();
    store({ ...state, hidden: [...state.hidden, `${issue.repo}#${issue.number}`] });
  },
  snooze: async (issue) => {
    const state = load();
    store({ ...state, hidden: [...state.hidden, `${issue.repo}#${issue.number}`] });
  },
  feedback: async () => undefined,
};

export function resetDemo() {
  store({ hidden: [] });
}
