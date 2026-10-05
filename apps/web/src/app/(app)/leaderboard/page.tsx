"use client";

import { ComingSoon } from "@/components/coming-soon";

export default function LeaderboardPage() {
  return (
    <main className="flex flex-col gap-4">
      <h1 className="text-3xl font-bold">Leaderboard</h1>
      <ComingSoon feature="leaderboard" title="Leaderboard and contribution rating">
        A weekly board of merged pull requests, and a rating that grows with accepted work only.
        It opens once enough people are active for it to mean something.
      </ComingSoon>
      <ComingSoon feature="weekly-challenges" title="Weekly challenges">
        A small challenge on a practice repo every week, the same for everyone.
      </ComingSoon>
    </main>
  );
}
