import { AppShell } from "./shell";
import { Providers } from "./providers";

// Everything under (app) needs a signed-in user. These are client components
// that fetch from FastAPI; the real check of the session happens there.
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <Providers>
      <AppShell>{children}</AppShell>
    </Providers>
  );
}
