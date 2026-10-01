import demoJson from "@core/demo/fixtures/demo.json";

// Mirrors issueradar.models and issueradar.demo.loader on the Python side.
// The Python tests validate the fixture; these types keep the web side honest.
export type Tier = "beginner" | "intermediate" | "pro";
export type Availability = "free" | "likely_free" | "claimed" | "has_pr" | "not_ready" | "unclear";
export type TimeBucket = "under_an_hour" | "half_a_day" | "a_weekend" | "a_week_or_more";
export type PullRequestStatus =
  | "waiting_for_review"
  | "changes_requested"
  | "approved"
  | "ci_failing"
  | "merge_conflict"
  | "stale"
  | "merged"
  | "closed_unmerged";

export interface DemoRepo {
  full_name: string;
  description: string;
  language: string;
  topics: string[];
  stars: number;
  health: { score: number; reasons: string[] };
}

export interface DemoIssue {
  repo: string;
  number: number;
  title: string;
  labels: string[];
  language: string;
  domain: string;
  issue_type: string;
  tier: Tier;
  difficulty_score: number;
  time_bucket: TimeBucket;
  availability: Availability;
  comments: number;
  created_at: string;
  updated_at: string;
  why_here: string;
  why_available: string[];
  why_tier: string[];
}

export interface DemoPullRequest {
  repo: string;
  number: number;
  title: string;
  status: PullRequestStatus;
  opened_at: string;
  last_activity_at: string;
  needs_you: string;
}

export interface DemoDataset {
  label: string;
  note: string;
  as_of: string;
  repos: DemoRepo[];
  issues: DemoIssue[];
  pull_requests: DemoPullRequest[];
}

export const demo = demoJson as DemoDataset;

export const TIER_DOTS: Record<Tier, number> = { beginner: 1, intermediate: 2, pro: 3 };

export function isRankable(a: Availability): boolean {
  return a === "free" || a === "likely_free";
}

// Acronyms keep their capitals in sentence case.
const ACRONYMS: Record<string, string> = { ci: "CI", pr: "PR" };

export function sentence(value: string): string {
  const words = value.split("_").map((w) => ACRONYMS[w] ?? w);
  const text = words.join(" ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}
