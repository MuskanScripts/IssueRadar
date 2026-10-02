import { brand } from "@/lib/brand";

export function Wordmark() {
  return (
    <span className="flex items-center gap-2.5 font-display text-[23px] font-extrabold tracking-[-0.02em] text-ink">
      <svg width="30" height="30" viewBox="0 0 30 30" fill="none" aria-hidden="true">
        <circle cx="15" cy="15" r="13" stroke="currentColor" strokeWidth="2" />
        <circle cx="15" cy="15" r="6.5" stroke="currentColor" strokeWidth="2" />
        <circle cx="22" cy="8.5" r="3.4" fill="var(--amber)" stroke="currentColor" strokeWidth="2" />
      </svg>
      <span>{brand.name}</span>
    </span>
  );
}
