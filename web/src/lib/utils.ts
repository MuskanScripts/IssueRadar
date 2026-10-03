import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

export function relativeDays(iso: string | null, now = Date.now()): string {
  if (!iso) return "unknown";
  const days = Math.floor((now - new Date(iso).getTime()) / 86_400_000);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  return `${days} days ago`;
}

export function pct(value: number | null): string {
  return value === null ? "n/a" : `${Math.round(value * 100)}%`;
}
