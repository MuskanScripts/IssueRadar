import { ImageResponse } from "next/og";
import { levelLabel, publicGet, type IssuePreview } from "@/lib/public";

export const alt = "An open-source issue on FirstPR";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const revalidate = 3600;

export default async function Image({
  params,
}: {
  params: Promise<{ owner: string; name: string; number: string }>;
}) {
  const { owner, name, number } = await params;
  const issue = await publicGet<IssuePreview>(`/issues/${owner}/${name}/${number}`, 3600);
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", justifyContent: "space-between", padding: 64, background: "#0e1419", color: "#e6edf3", fontFamily: "sans-serif" }}>
        <div style={{ display: "flex", fontSize: 30, color: "#3fc1b3", fontWeight: 700 }}>FirstPR</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div style={{ display: "flex", fontSize: 30, color: "#93a3b2" }}>
            {issue ? `${issue.repo} #${issue.number}` : `${owner}/${name} #${number}`}
          </div>
          <div style={{ display: "flex", fontSize: 60, fontWeight: 700, lineHeight: 1.15 }}>
            {(issue?.title ?? "An open-source issue").slice(0, 90)}
          </div>
        </div>
        <div style={{ display: "flex", gap: 24, fontSize: 30 }}>
          {issue ? <span>{levelLabel[issue.tier]}</span> : null}
          {issue ? <span>{issue.time_label}</span> : null}
          {issue?.language ? <span>{issue.language}</span> : null}
          <span style={{ color: "#5fd48a" }}>{issue?.availability_label ?? "Free"}</span>
        </div>
      </div>
    ),
    size,
  );
}
