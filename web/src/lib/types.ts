// Mirrors the API's response models (src/issueradar/api/app.py, OpenAPI at /api/docs).

export type Tier = "beginner" | "intermediate" | "pro";

export interface Meta {
  name: string;
  version: string;
  tagline: string;
  demo: boolean;
  token_configured: boolean;
}

export interface Issue {
  repo: string;
  number: number;
  title: string;
  url: string | null;
  labels: string[];
  language: string | null;
  stars: number;
  comments: number;
  updated_at: string | null;
  availability: string;
  availability_label: string;
  availability_reasons: string[];
  tier: Tier;
  difficulty_score: number;
  time_bucket: string;
  issue_type: string;
  difficulty_reasons: string[];
  discussion_first: boolean;
  health: number | null;
  health_reasons: string[];
  flags: Record<string, unknown>;
  stack_fit: number;
  stack_reasons: string[];
  rank: number | null;
  rank_parts: Record<string, number>;
  why: string;
  frameworks: string[];
  domains: string[];
  checklist: string[];
}

export interface Repo {
  full_name: string;
  description: string | null;
  language: string | null;
  stars: number;
  archived: boolean;
  health: number | null;
  health_parts: Record<string, number | null>;
  health_reasons: string[];
  open_issues: number;
  free_issues: number;
  last_synced_at: string | null;
  pushed_at: string | null;
  sync_error: string | null;
}

export interface TimelineEvent {
  at: string;
  actor: string | null;
  kind: string;
  text: string;
}

export interface Pull {
  repo: string;
  number: number;
  title: string;
  url: string | null;
  status: string;
  status_label: string;
  needs_you: string;
  reasons: string[];
  nudge: string | null;
  draft: boolean;
  days_quiet: number;
  opened_at: string | null;
  closed_at: string | null;
  timeline: TimelineEvent[];
}

export interface Insights {
  opened: number;
  merged: number;
  closed_unmerged: number;
  open_now: number;
  merge_rate: number | null;
  median_hours_to_first_review: number | null;
  by_month: { month: string; opened: number; merged: number }[];
}

export interface SettingsInfo {
  token_configured: boolean;
  database: string;
  last_sync: {
    status: string;
    started_at: string;
    finished_at: string | null;
    requests: number;
    not_modified: number;
    repos_done: number;
    repos_failed: number;
  } | null;
  channels: Record<string, boolean>;
  limits: Record<string, number>;
  weights: Record<string, number>;
}

export interface DigestPreview {
  title: string;
  markdown: string;
  html: string;
  items: number;
}

export type Level = "learning" | "medium" | "strong";

export interface Profile {
  stretch: boolean;
  languages: Record<string, Level>;
  frameworks: Record<string, Level>;
  domains: Record<string, Level>;
  prefer_issue_types: string[];
}

export interface Filters {
  level: Tier[];
  language: string[];
  type: string[];
  time: string[];
  min_health: number | null;
  max_comments: number | null;
  no_discussion: boolean;
  q: string;
}

export interface SavedView {
  name: string;
  filters: Partial<Filters>;
}

export const EMPTY_FILTERS: Filters = {
  level: [],
  language: [],
  type: [],
  time: [],
  min_health: null,
  max_comments: null,
  no_discussion: false,
  q: "",
};

export function issueKey(issue: Pick<Issue, "repo" | "number">): string {
  return `${issue.repo}#${issue.number}`;
}
