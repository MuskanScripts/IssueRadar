import { ImageResponse } from "next/og";
import { publicGet, type PublicProfile } from "@/lib/public";

export const alt = "A FirstPR profile";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const revalidate = 3600;

export default async function Image({ params }: { params: Promise<{ handle: string }> }) {
  const { handle } = await params;
  const p = await publicGet<PublicProfile>(`/profiles/${handle}`, 3600);
  const stats: [string, number][] = p
    ? [
        ["merged pull requests", p.merged],
        ["repos", p.repos],
        ["XP", p.xp],
        ["day best streak", p.best_streak],
      ]
    : [];
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", justifyContent: "space-between", padding: 64, background: "#0e1419", color: "#e6edf3", fontFamily: "sans-serif" }}>
        <div style={{ display: "flex", fontSize: 30, color: "#3fc1b3", fontWeight: 700 }}>FirstPR</div>
        <div style={{ display: "flex", alignItems: "center", gap: 36 }}>
          {p?.avatar_url ? (
            <img src={p.avatar_url} width={160} height={160} style={{ borderRadius: 80 }} alt="" />
          ) : null}
          <div style={{ display: "flex", flexDirection: "column" }}>
            <div style={{ display: "flex", fontSize: 64, fontWeight: 700 }}>{p?.name ?? p?.handle ?? handle}</div>
            <div style={{ display: "flex", fontSize: 34, color: "#93a3b2" }}>@{p?.handle ?? handle}</div>
          </div>
        </div>
        <div style={{ display: "flex", gap: 48 }}>
          {stats.map(([label, value]) => (
            <div key={label} style={{ display: "flex", flexDirection: "column" }}>
              <span style={{ fontSize: 56, fontWeight: 700, color: "#6ad8c8" }}>{value}</span>
              <span style={{ fontSize: 24, color: "#93a3b2" }}>{label}</span>
            </div>
          ))}
        </div>
      </div>
    ),
    size,
  );
}
