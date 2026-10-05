import type { NextConfig } from "next";

// In production a reverse proxy sends /api to FastAPI before Next.js sees it.
// This rewrite does the same during `npm run dev`, when there is no proxy.
// API_INTERNAL_HOSTPORT is what Render hands a private service ("host:port").
// Read at build time, so the web Dockerfile takes both as build arguments.
const apiUrl =
  process.env.API_INTERNAL_URL ??
  (process.env.API_INTERNAL_HOSTPORT ? `http://${process.env.API_INTERNAL_HOSTPORT}` : "http://localhost:8000");

// Security headers for every page. Next.js needs inline scripts and styles for its
// own bootstrapping; everything else comes from this site, and avatars from GitHub.
const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${process.env.NODE_ENV === "production" ? "" : " 'unsafe-eval'"}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: https://avatars.githubusercontent.com",
  "font-src 'self'",
  "connect-src 'self'",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: csp },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

const config: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  // Compressing would hold back server-sent events (live workspace steps and
  // notifications) when /api goes through the rewrite below. The proxy in front
  // compresses in production.
  compress: false,
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/api/:path*` }];
  },
};

export default config;
