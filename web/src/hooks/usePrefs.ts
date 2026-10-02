import { useCallback, useState } from "react";

/** A small per-browser preference (density and the like), safe when storage is blocked. */
export function usePref<T extends string>(key: string, fallback: T): [T, (value: T) => void] {
  const [value, setValue] = useState<T>(() => {
    try {
      return (localStorage.getItem(key) as T | null) ?? fallback;
    } catch {
      return fallback;
    }
  });
  const set = useCallback(
    (next: T) => {
      setValue(next);
      try {
        localStorage.setItem(key, next);
      } catch {
        /* not persisted */
      }
    },
    [key],
  );
  return [value, set];
}
