import { NextResponse } from "next/server";

// The Feedback link on every page. Set FEEDBACK_URL to a form or a GitHub issue
// template; without it, feedback goes to the repo's issues.
export function GET() {
  const target =
    process.env.FEEDBACK_URL ??
    "https://github.com/MuskanScripts/IssueRadar/issues/new?labels=feedback&title=Feedback%3A+";
  return NextResponse.redirect(target, 302);
}
