import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "FirstPR", template: "%s · FirstPR" },
  description: "Your first merged pull request, picked for you today.",
  icons: { icon: "/favicon.svg" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
