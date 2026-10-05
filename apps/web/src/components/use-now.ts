"use client";

import { useEffect, useState } from "react";

/** The current time, updated every `everyMs`, for countdowns. */
export function useNow(everyMs = 30_000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), everyMs);
    return () => window.clearInterval(id);
  }, [everyMs]);
  return now;
}

export function timeLeft(untilIso: string, now: number) {
  const minutes = Math.max(0, Math.round((new Date(untilIso).getTime() - now) / 60_000));
  const hours = Math.floor(minutes / 60);
  return hours ? `${hours} h ${minutes % 60} min` : `${minutes} min`;
}
