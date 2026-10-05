import Link from "next/link";
import { Providers } from "./providers";

// Everything under (app) is the signed-in product: client components that fetch
// from FastAPI. Sign-in arrives in Step 2; until then these pages are open.
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <Providers>
      <div className="mx-auto flex max-w-5xl flex-col gap-6 px-4 py-6">
        <nav className="flex items-center gap-6 border-b border-line pb-4">
          <Link href="/" className="text-lg font-bold">
            FirstPR
          </Link>
          <Link href="/home" className="text-ink-2 hover:text-ink">
            Home
          </Link>
        </nav>
        {children}
      </div>
    </Providers>
  );
}
