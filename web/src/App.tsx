import { lazy, Suspense, type ReactNode } from "react";
import { BrowserRouter, MemoryRouter, Route, Routes } from "react-router";

import { AppShell } from "@/components/AppShell";
import { Loading } from "@/components/ui/states";
import { DataProvider } from "@/lib/data";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { RadarPage } from "@/pages/RadarPage";

// The radar is the first screen and ships in the main bundle; the other pages
// (Insights carries the chart library) load when first opened.
const ReposPage = lazy(() => import("@/pages/ReposPage").then((m) => ({ default: m.ReposPage })));
const PrsPage = lazy(() => import("@/pages/PrsPage").then((m) => ({ default: m.PrsPage })));
const ProfilePage = lazy(() => import("@/pages/ProfilePage").then((m) => ({ default: m.ProfilePage })));
const DigestPage = lazy(() => import("@/pages/DigestPage").then((m) => ({ default: m.DigestPage })));
const InsightsPage = lazy(() => import("@/pages/InsightsPage").then((m) => ({ default: m.InsightsPage })));
const SettingsPage = lazy(() => import("@/pages/SettingsPage").then((m) => ({ default: m.SettingsPage })));

const page = (element: ReactNode) => <Suspense fallback={<Loading rows={3} />}>{element}</Suspense>;

function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<RadarPage />} />
        <Route path="repos" element={page(<ReposPage />)} />
        <Route path="prs" element={page(<PrsPage />)} />
        <Route path="profile" element={page(<ProfilePage />)} />
        <Route path="digest" element={page(<DigestPage />)} />
        <Route path="insights" element={page(<InsightsPage />)} />
        <Route path="settings" element={page(<SettingsPage />)} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}

/** ``initialPath`` and ``demo`` are for tests; the real app uses the browser URL. */
export function App({ initialPath, demo }: { initialPath?: string; demo?: boolean }) {
  const content = <AppRoutes />;
  return (
    <DataProvider demo={demo}>
      {initialPath ? (
        <MemoryRouter initialEntries={[initialPath]}>{content}</MemoryRouter>
      ) : (
        <BrowserRouter>{content}</BrowserRouter>
      )}
    </DataProvider>
  );
}
