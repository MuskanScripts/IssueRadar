import type { MetadataRoute } from "next";
import { siteUrl } from "@/lib/public";

export default function robots(): MetadataRoute.Robots {
  return {
    // Signed-in pages and the API are not for search engines.
    rules: [{ userAgent: "*", allow: "/", disallow: ["/api/", "/home", "/explore", "/issues/", "/workspaces", "/pulls", "/progress", "/profile", "/settings", "/notifications", "/onboarding", "/admin"] }],
    sitemap: `${siteUrl()}/sitemap.xml`,
  };
}
