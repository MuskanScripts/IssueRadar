import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  // Makes links in metadata and preview images absolute (set SITE_URL in production).
  metadataBase: new URL(process.env.SITE_URL ?? "http://localhost:8080"),
  title: { default: "FirstPR", template: "%s · FirstPR" },
  description: "Your first merged pull request, picked for you today.",
  icons: { icon: "/favicon.svg" },
  openGraph: { siteName: "FirstPR", type: "website" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
