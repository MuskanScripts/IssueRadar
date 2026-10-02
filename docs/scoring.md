# How scores are computed

Every number IssueRadar shows comes from the rules on this page. All weights,
thresholds and word lists live in
[`src/issueradar/config/defaults.yaml`](../src/issueradar/config/defaults.yaml),
and your own `firstpr.yaml` can change any of them. `firstpr explain <issue-url>`
prints the reasons behind each result for a single issue.

Nothing here uses an AI model. The same inputs always give the same answer.

## 1. Is it free? (availability)

Code: [`engine/availability.py`](../src/issueradar/engine/availability.py)

The checks run in this order. The first one that decides stops the rest.

| # | Check | Result |
| --- | --- | --- |
| 1 | Issue is not open | UNCLEAR |
| 2 | Conversation is locked | NOT_READY |
| 3 | Has a label the repo reserves for maintainers (repo rules) | NOT_READY |
| 4 | Has a "not ready" label (repo rules plus `availability.not_ready_labels`) | NOT_READY |
| 5 | Opened by a bot | UNCLEAR |
| 6 | Has an assignee | CLAIMED |
| 7 | A human, open or merged PR is linked: closing keyword in an open PR ("fixes #12"), GitHub's `linked:pr` search, a hand-made link on GitHub, or a PR that references it in the timeline | HAS_PR |
| 8 | Only a plain mention in an open PR's text, and the timeline was not checked | UNCLEAR |
| 9 | Title and body don't look like English | UNCLEAR |
| 10 | Has comments that were not read yet | UNCLEAR |
| 11 | An outside commenter claimed it ("can I work on this", "/assign", ...) and didn't give it back | CLAIMED, or LIKELY_FREE when the claim is `stale_claim_days` (14) days old or more |
| 12 | None of the above | FREE |

Details:

- "Outside" means the comment's `author_association` is not OWNER, MEMBER or
  COLLABORATOR. A maintainer writing "feel free to take this" is an
  invitation: it's shown as a positive reason and never counts as a claim.
- A claim is given back when the same person later writes something from
  `release_patterns` ("can't work on this", "unassign me").
- Phrases match whole words only, so "reassign" doesn't match "assign".
- Bot PRs (Dependabot, Renovate) and bot comments are ignored. Bot PR bodies
  copy other projects' release notes, which produced up to 159 false issue
  numbers per PR on real data (RESULTS.md).
- English check: under 70% ASCII letters, or 25+ words with under 4% common
  English words.

Only FREE and LIKELY_FREE issues are ranked.

### Where the PR signals come from

| Layer | Source | Cost |
| --- | --- | --- |
| 1 | `repo:o/r is:issue is:open linked:pr` search, one per repo | search budget |
| 2 | Open PR titles and bodies, split into closing references and plain mentions | free (already synced) |
| 3 | Issue timeline: `cross-referenced` from a PR, `connected` / `disconnected` | one request per finalist, 304 when unchanged |

Comments and timelines are read only for **finalists**: open issues with no
assignee, no linked PR and no closing reference, most recently updated first,
up to `enrich.max_issues_per_repo` (30) per repo.

## 2. Level (difficulty)

Code: [`engine/difficulty.py`](../src/issueradar/engine/difficulty.py)

```
score = starting point + sum(adjustments), clamped to 0..100
tier  = Beginner 0-33, Intermediate 34-66, Pro 67-100
```

**Starting point.** Labels are looked up in the repo's own label map first,
then in `difficulty.label_tiers`. A mapped label starts the score at its tier
anchor: Beginner 15, Intermediate 50, Pro 80. Several mapped labels: their
average. No mapped label: `base_score` (45).

**Adjustments** (each counted once):

| Signal | Points | How it is detected |
| --- | --- | --- |
| Docs or typo work | -15 | `keywords.docs_or_typo` in title, body or labels |
| Test work | -10 | `keywords.tests_only` |
| Has code or a repro | -5 | a code block, or `keywords.repro` |
| Names a file | -5 | a path like `src/app/main.py` in the body |
| Short body | -5 | under 400 characters |
| Long body | +10 | over 3,000 characters |
| Long discussion | +10 | 10 or more comments |
| Links other issues | +5 each, up to 3 | `#123` references in the body |
| Needs discussion first | +20 | `keywords.discussion_first`, or the repo's own words |
| Performance or concurrency | +15 | `keywords.performance_or_concurrency` |
| Security-sensitive | +10 | `keywords.security` |

**Time estimate** from the final score: up to 20 under an hour, up to 45 half
a day, up to 70 a weekend, above that a week or more.

**Issue type** (docs, tests, ci, refactor, bug, feature): the first group of
words found in the title or labels, in that order.

You will be able to mark an issue "harder" or "easier than it looked"
(`difficulty_feedback` table, used from M5). Those marks will tune the
adjustments, and the evaluation harness measures accuracy against your labels.

## 3. Repo health (0 to 100)

Code: [`engine/health.py`](../src/issueradar/engine/health.py)

```
health = 30 * first_response + 30 * outside_merge_rate + 20 * recent_commit
       + 10 * pr_backlog + 10 * contributor_docs
```

Each part is between 0 and 1. "Scaled" means: 1 at or under the good value, 0
at or over the bad value, a straight line in between.

| Part | Measure | Scale |
| --- | --- | --- |
| first_response | Median days from an outsider's issue to a maintainer's first comment, over issues whose comments were read | good 2, bad 30 |
| outside_merge_rate | Accepted / decided among the last 100 closed PRs by outsiders (no bots, no maintainers). Accepted = merged, or matching the repo's bot-import rule | already 0..1 |
| recent_commit | Days since the last push | good 7, bad 180 |
| pr_backlog | Open pull requests | good 10, bad 100 |
| contributor_docs | CONTRIBUTING 0.5, issue template or issue forms 0.25, PR template 0.25 | already 0..1 |

A part with fewer than 3 data points is unknown: it scores 0.5 and the reasons
say "not enough". An archived repo scores 0. Health is cached for 24 hours.

**Flags** (shown under "Before you start", not part of the score), read from
CONTRIBUTING and repo rules: CLA required, DCO sign-off required, a policy on
AI tools, and "open an issue before a pull request".

## 4. Stack fit

Code: [`engine/stack.py`](../src/issueradar/engine/stack.py)

The issue's technologies:

- **languages**: file extensions named in the issue body if any, otherwise the
  repo's biggest language (from `GET /repos/{o}/{r}/languages`);
- **frameworks**: dependencies in the repo's root manifest files, mapped with
  `stack.frameworks`;
- **domains**: the repo's topics, mapped with `stack.domains`.

Each one found in your `skills.yaml` contributes its level: strong 1.0, medium
0.7, learning 0.4.

```
stack_fit = (average of matched levels + best matched level) / 2
```

Nothing matched: 0. No `skills.yaml`: 0.5 for everything.

**Target level.** From your level in the issue's language: learning or medium
gives Beginner, strong gives Intermediate. `stretch: true` moves it up one tier.

```
tier_fit = 1 if the issue's tier is the target, 0.5 one tier away, 0 otherwise
```

## 5. Ranking

Code: [`engine/ranking.py`](../src/issueradar/engine/ranking.py)

```
rank = 0.35 * tier_fit + 0.25 * health / 100 + 0.20 * stack_fit
     + 0.10 * freshness + 0.10 * low_competition

freshness       = 0.5 ** (days since last update / 30)
low_competition = 1 - min(comments / 10, 1), halved for LIKELY_FREE
```

A repo with no health score yet counts as 50. Each ranked issue also gets one
line saying why it is there, built from the parts that stand out.

## 6. Checking the engines

`firstpr eval run eval/labels.csv` compares these rules with issues you
labelled by hand: precision and recall for FREE (strict: only FREE counts;
lenient: FREE or LIKELY_FREE), and tier accuracy. See
[`eval/README.md`](../eval/README.md). Results go in [RESULTS.md](../RESULTS.md)
with the command that produced them.
