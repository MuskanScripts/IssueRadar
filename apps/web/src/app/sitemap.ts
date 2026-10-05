import type { MetadataRoute } from "next";
import { connection } from "next/server";
import { publicGet, siteUrl } from "@/lib/public";

// Built on request (the API caches the list for an hour), not at build time.
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  await connection();
  const data = await publicGet<{ entries: { path: string; updated_at: string | null }[] }>(
    "/sitemap",
    3600,
  );
  const entries = data?.entries ?? [{ path: "/", updated_at: null }, { path: "/trending", updated_at: null }];
  return entries.map((e) => ({
    url: `${siteUrl()}${e.path}`,
    lastModified: e.updated_at ?? undefined,
  }));
}
