// Data for the public pages, fetched on the server and cached by Next.js.
import { serverApiUrl } from "./api";

export type PublicStats = {
  free_issues: number;
  repos: number;
  people: number;
  merged_this_week: number;
  merged_total: number;
};

export type PublicIssue = {
  repo: string;
  number: number;
  title: string;
  language: string | null;
  tier: "beginner" | "intermediate" | "pro";
  time_label: string;
  labels: string[];
  health: number | null;
  comments: number;
  updated_at: string | null;
  why_free: string | null;
};

export type IssuePreview = PublicIssue & {
  repo_description: string | null;
  availability: string;
  availability_label: string;
  url: string | null;
  checklist: string[];
  difficulty_reasons: string[];
  health_reasons: string[];
};

export type IssueList = { items: PublicIssue[] };

export type MergedItem = {
  repo: string;
  number: number;
  title: string;
  url: string | null;
  merged_at: string | null;
  handle: string | null;
};

export type Trending = {
  tab: string;
  issues: PublicIssue[];
  repos: { repo: string; description: string | null; language: string | null; free_issues: number; health: number | null }[];
  merged: MergedItem[];
};

export type PublicProfile = {
  handle: string;
  name: string | null;
  avatar_url: string | null;
  xp: number;
  streak: number;
  best_streak: number;
  merged: number;
  repos: number;
  badges: string[];
  skills: string[];
  calendar: { day: string; minutes: number; green: boolean }[];
  merged_pulls: MergedItem[];
};

/** The site's own address, for links in metadata, the sitemap and preview images. */
export const siteUrl = () => (process.env.SITE_URL ?? "http://localhost:8080").replace(/\/$/, "");

/** A public API call from the server. Null when the API is down or says no, so a
 * page still renders (for example during `next build`, when no API runs). */
export async function publicGet<T>(path: string, revalidate: number): Promise<T | null> {
  try {
    const resp = await fetch(`${serverApiUrl()}/api/v1/public${path}`, { next: { revalidate } });
    if (!resp.ok) return null;
    return (await resp.json()) as T;
  } catch {
    return null;
  }
}

export const levelLabel = { beginner: "Beginner", intermediate: "Intermediate", pro: "Pro" } as const;
