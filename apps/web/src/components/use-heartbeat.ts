"use client";

import { useEffect } from "react";
import { send } from "@/lib/api";

const EVERY_MS = 60_000;

/** Counts active minutes for the calendar. Once a minute, and only while the tab is
 * visible, it tells the API how long ago the user last did something on the page.
 * The API counts the minute only when that was under 2 minutes ago. */
export function useHeartbeat() {
  useEffect(() => {
    let lastInput = Date.now();
    const touched = () => {
      lastInput = Date.now();
    };
    const events = ["keydown", "pointerdown", "pointermove", "wheel", "scroll", "touchstart"];
    for (const name of events) window.addEventListener(name, touched, { passive: true });

    const beat = () => {
      if (document.visibilityState !== "visible") return; // background tabs send nothing
      const idle = Math.round((Date.now() - lastInput) / 1000);
      void send("/api/v1/me/heartbeat", {
        json: { visible: true, idle_seconds: idle },
      }).catch(() => undefined);
    };
    const timer = window.setInterval(beat, EVERY_MS);
    return () => {
      window.clearInterval(timer);
      for (const name of events) window.removeEventListener(name, touched);
    };
  }, []);
}
