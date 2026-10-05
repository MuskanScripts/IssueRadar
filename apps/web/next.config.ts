import type { NextConfig } from "next";

// In production a reverse proxy sends /api to FastAPI before Next.js sees it.
// This rewrite does the same during `npm run dev`, when there is no proxy.
const apiUrl = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

const config: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  // Compressing would hold back server-sent events (live workspace steps and
  // notifications) when /api goes through the rewrite below. The proxy in front
  // compresses in production.
  compress: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/api/:path*` }];
  },
};

export default config;
