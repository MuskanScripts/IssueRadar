# Roadmap

What is done, what is next, and what is deliberately not planned. The detailed
plan with "done when" checks is in [PLAN.md](PLAN.md).

## Done

- **M0 to M2.** Read-only GitHub client with rate-limit budgets and ETag cache;
  watchlist and sync; availability, difficulty, repo health, stack fit and
  ranking with a reason for every result.
- **M3.** Daily digest over Markdown, RSS, email, Telegram, Discord and Slack,
  without repeats.
- **M4.** Pull request tracker with statuses and nudge drafts you send yourself.
- **M5.** Local dashboard and API, demo mode.
- **M6.** GitHub Action and template repo, Docker image and Compose, PyPI
  packaging, release automation, landing page, docs.

## Next

- **Real-world numbers.** Hand-label at least 50 issues and publish precision
  and recall for "is it free" and tier accuracy in RESULTS.md.
- **Verified starter packs.** Check each pack's repos and mark them verified.
- **Feedback from other people.** Five people try it from the README alone.

## Later, only if people use it

- **M7. Hosted mode** behind a feature flag: sign in with GitHub (no write
  scopes), encrypted tokens, Postgres, shared crawler, delete-my-data, privacy
  policy and terms. Starts only after M0 to M6 ship and others use them.
- **M8 (optional). MCP server** with read-only tools (`find_issues`,
  `explain_issue`, `my_prs`).
- **M9 (optional). Classifier experiment**, shipped only if it beats the rules
  on the hand-labelled set.

## Not planned

- Anything that writes to GitHub: comments, assignments, stars, follows, forks
  or pull requests. Nudges stay drafts.
- Scraping github.com pages. Only the documented API is used.
- An AI model in the scoring path. The rules stay explainable.
