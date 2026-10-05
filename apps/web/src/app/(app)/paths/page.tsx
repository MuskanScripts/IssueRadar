"use client";

import { ComingSoon } from "@/components/coming-soon";

export default function PathsPage() {
  return (
    <main className="flex flex-col gap-4">
      <h1 className="text-3xl font-bold">Paths</h1>
      <ComingSoon feature="career-paths" title="Career paths">
        Ordered sets of issues that build one skill step by step, for example &quot;Your first
        five Python contributions&quot;.
      </ComingSoon>
      <ComingSoon feature="teams" title="Universities and teams">
        Classes and teams working through issues together, with a shared view for the teacher or
        lead.
      </ComingSoon>
      <ComingSoon feature="vscode-extension" title="VS Code extension">
        Your workspace time counted exactly, straight from the editor.
      </ComingSoon>
    </main>
  );
}
