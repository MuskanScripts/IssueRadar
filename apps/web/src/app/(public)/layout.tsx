import Link from "next/link";
import { SignInLink } from "@/components/track";
import { signInUrl } from "@/lib/api";

export default function PublicLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto flex min-h-screen max-w-5xl flex-col px-4">
      <header className="flex flex-wrap items-center gap-x-6 gap-y-2 py-5">
        <Link href="/" className="text-xl font-bold">
          FirstPR
        </Link>
        <Link href="/trending" className="text-ink-2 hover:text-ink">
          Trending
        </Link>
        <SignInLink
          href={signInUrl("/home")}
          from="header"
          className="ml-auto rounded-md bg-accent px-4 py-2 font-semibold text-accent-ink hover:opacity-90"
        >
          Sign in with GitHub
        </SignInLink>
      </header>
      <div className="flex-1">{children}</div>
      <footer className="mt-12 flex flex-wrap gap-x-6 gap-y-2 border-t border-line py-6 text-sm text-ink-2">
        <span>FirstPR helps you make your first open-source contributions.</span>
        <a href="/maintainers" className="underline">
          For maintainers
        </a>
        <a href="/feedback" className="underline">
          Feedback
        </a>
        <a href="https://github.com/MuskanScripts/IssueRadar" className="underline">
          Source code
        </a>
      </footer>
    </div>
  );
}
