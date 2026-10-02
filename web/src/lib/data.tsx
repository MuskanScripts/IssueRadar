import { QueryClient, QueryClientProvider, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

import { demoSource } from "./demo-source";
import { httpSource, type DataSource } from "./source";
import type { Issue, Profile, SavedView } from "./types";

const DEMO_KEY = "demo-mode";

function initialDemo(): boolean {
  if (typeof window === "undefined") return false;
  const param = new URLSearchParams(window.location.search).get("demo");
  if (param === "1" || param === "0") {
    try {
      localStorage.setItem(DEMO_KEY, param);
    } catch {
      /* not persisted */
    }
    return param === "1";
  }
  try {
    return localStorage.getItem(DEMO_KEY) === "1";
  } catch {
    return false;
  }
}

interface DataContextValue {
  source: DataSource;
  demo: boolean;
  setDemo(on: boolean): void;
}

const DataContext = createContext<DataContextValue | null>(null);

export function DataProvider({ children, demo: forced }: { children: ReactNode; demo?: boolean }) {
  const [demo, setDemoState] = useState<boolean>(forced ?? initialDemo);
  const [client] = useState(
    () => new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 30_000 } } }),
  );
  const setDemo = useCallback(
    (on: boolean) => {
      try {
        localStorage.setItem(DEMO_KEY, on ? "1" : "0");
      } catch {
        /* not persisted */
      }
      setDemoState(on);
      client.clear();
    },
    [client],
  );
  const value = useMemo(() => ({ source: demo ? demoSource : httpSource, demo, setDemo }), [demo, setDemo]);
  return (
    <QueryClientProvider client={client}>
      <DataContext.Provider value={value}>{children}</DataContext.Provider>
    </QueryClientProvider>
  );
}

export function useData(): DataContextValue {
  const value = useContext(DataContext);
  if (!value) throw new Error("useData must be used inside <DataProvider>");
  return value;
}

export function useMeta() {
  const { source, demo } = useData();
  return useQuery({ queryKey: ["meta", demo], queryFn: () => source.meta() });
}

export function useIssues(all = false) {
  const { source, demo } = useData();
  return useQuery({ queryKey: ["issues", demo, all], queryFn: () => source.issues(all) });
}

export function useRepos() {
  const { source, demo } = useData();
  return useQuery({ queryKey: ["repos", demo], queryFn: () => source.repos() });
}

export function usePulls() {
  const { source, demo } = useData();
  return useQuery({ queryKey: ["pulls", demo], queryFn: () => source.pulls() });
}

export function useInsights() {
  const { source, demo } = useData();
  return useQuery({ queryKey: ["insights", demo], queryFn: () => source.insights() });
}

export function useSettingsInfo() {
  const { source, demo } = useData();
  return useQuery({ queryKey: ["settings", demo], queryFn: () => source.settings() });
}

export function useDigest() {
  const { source, demo } = useData();
  return useQuery({ queryKey: ["digest", demo], queryFn: () => source.digest() });
}

export function useProfile() {
  const { source, demo } = useData();
  return useQuery({ queryKey: ["profile", demo], queryFn: () => source.profile() });
}

export function useViews() {
  const { source, demo } = useData();
  return useQuery({ queryKey: ["views", demo], queryFn: () => source.views() });
}

export function useSaveProfile() {
  const { source } = useData();
  const client = useQueryClient();
  return useMutation({
    mutationFn: (profile: Profile) => source.saveProfile(profile),
    onSuccess: () => client.invalidateQueries(),
  });
}

export function useSaveViews() {
  const { source } = useData();
  const client = useQueryClient();
  return useMutation({
    mutationFn: (views: SavedView[]) => source.saveViews(views),
    onSuccess: () => client.invalidateQueries({ queryKey: ["views"] }),
  });
}

export function useIssueActions() {
  const { source } = useData();
  const client = useQueryClient();
  const refresh = () => client.invalidateQueries({ queryKey: ["issues"] });
  return {
    dismiss: useMutation({ mutationFn: (i: Issue) => source.dismiss(i), onSuccess: refresh }),
    snooze: useMutation({ mutationFn: (i: Issue) => source.snooze(i, 7), onSuccess: refresh }),
    feedback: useMutation({
      mutationFn: ({ issue, verdict }: { issue: Issue; verdict: "harder" | "easier" | "about_right" }) =>
        source.feedback(issue, verdict),
    }),
  };
}
