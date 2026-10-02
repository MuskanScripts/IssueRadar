# Results

Measured numbers only. Each entry gives the date, the environment and the exact
command, so anyone can rerun it. Demo data never appears here.

## M1: conditional requests (ETag / 304)

**Question.** GitHub's docs say an authenticated `304 Not Modified` does not
count against the primary rate limit. One third-party library says this is
unreliable. Does a 304 cost budget?

**Command** (three requests: plain GET, conditional GET, plain GET; prints
`x-ratelimit-used` after each):

```powershell
firstpr doctor --measure-etag MuskanScripts/IssueRadar
```

**Environment.** 2026-10-02, Linux build container. Requests went through the
container's GitHub proxy, which adds its own credentials (the responses show a
15,000 per hour limit, so they were authenticated, but not with a personal
token). `authenticated: False` in the output means no token was set in
FirstPR itself.

| Run | Statuses | `x-ratelimit-used` after each | 304 cost |
| --- | --- | --- | --- |
| 1 | 200, 304, 200 | 53, 54, 55 | 1 |
| 2 | 200, 304, 200 | 58, 58, 59 | 0 |
| 3 | 200, 304, 200 | 60, 60, 61 | 0 |
| 4 | 200, 304, 200 | 62, 62, 63 | 0 |
| 5 | 200, 304, 200 | 64, 64, 65 | 0 |
| 6 | 200, 304, 200 | 66, 66, 67 | 0 |
| 7 | 200, 304, 200 | 68, 68, 69 | 0 |

**Result.** In 6 of 7 runs the 304 cost nothing. In run 1 the counter moved by
one. The token is shared by other tools in that container, so another request
in between cannot be ruled out, and GitHub's docs say the counters can differ
between regions. Conclusion: 304s are free in practice, but FirstPR does not
assume they are; the budgeter always trusts the latest headers.

**Still to do.** Repeat with a personal fine-grained token on Windows:
`$env:FIRSTPR_GITHUB_TOKEN` set, same command. Add the rows here.

## M1: ETag savings on a second sync

**Command:**

```powershell
firstpr watch add MuskanScripts/IssueRadar
firstpr sync
firstpr sync
```

**Environment.** Same container and proxy as above, 2026-10-02, a fresh database.

| Run | Requests | Answered by 304 | `core` remaining after |
| --- | --- | --- | --- |
| First sync | 3 | 0 | 14943 |
| Second sync | 3 | 3 | 14943 |

The second sync sent the same three requests (repo, open issues, open pull
requests), all came back as 304 from the cache, and the remaining budget did
not change. This is one small repository; the 25-repository measurement from
the brief needs a personal token and is still to do.

## M1: scanning PR text for issue numbers (layer 2)

**Question.** The brief suggests scanning open PR titles and bodies for
`#123` to catch PRs that work on an issue without a closing reference. Does it
work on real data?

**Data.** The 11 open pull requests on MuskanScripts/IssueRadar recorded on
2026-10-02 (`tests/fixtures/github/recorded/muskanscripts-issueradar-pulls-open.json`).
All 11 are Dependabot PRs.

**First attempt** (every `#n` in title and body counted): 10 of 11 PRs
"referenced" between 1 and 159 issue numbers, none of which are issues in this
repository. Dependabot copies upstream release notes into the PR body, and
those notes are full of other projects' issue numbers. In a large repository
these numbers would collide with real issues and wrongly mark them as taken.

**Change.** References are now split into `closing_issues` (GitHub's closing
keywords such as "fixes #12", a strong signal) and `mentioned_issues` (any
other reference, a weak signal), and bodies of bot-authored PRs are not
scanned. On the same data: 0 false references. Covered by
`tests/test_normalize.py::test_bot_pr_bodies_are_not_scanned_on_real_data`.
The availability engine (M2) will weigh the two kinds differently.

## M2: FREE detection and tier accuracy

**Not measured yet.** These numbers need issues labelled by a person, and none
are labelled yet. The command exists and is tested; the tests use made-up
labels for a made-up repo, which are not results.

To produce the numbers (see [eval/README.md](eval/README.md)):

```powershell
firstpr pack add ai-agents-and-mcp
firstpr sync
firstpr eval sample --out eval/labels.csv --per-repo 25
# label at least 50 rows by hand, then:
firstpr eval run eval/labels.csv --json eval/results.json
```

Paste the output here with the date and the commit it ran on.

## M3: digest generation time

**Target:** under 5 seconds from cache.

**Command:** `python scripts/bench_digest.py 25 200`

**Data:** a generated database of 25 repos with 200 open issues each (5,000
issues), built from GitHub's documented issue shape. It measures speed only and
says nothing about real repositories. Linux build container, Python 3.13,
2026-10-02.

| Version | Time |
| --- | --- |
| First version (each issue queried its repo's PRs and its own signals) | 9.59 s, 9.49 s |
| PRs and signals loaded once per run | 4.98 s |
| Plus one compiled pattern per phrase list, language check on the first 2,000 characters | 1.80 s, 2.20 s, 2.44 s |

**Result:** about 2 seconds for 5,000 issues, under the target.

## M3: running the digest twice

`tests/test_digest.py::test_digest_send_twice_sends_nothing_new` runs
`firstpr digest --send` twice on the test repo. The first run writes the
Markdown file and the RSS feed; the second prints "Nothing new since the last
digest, so nothing was sent." and the feed file is byte-for-byte unchanged.

## M5: dashboard

**First load.** Target: under 2 seconds locally. Built dashboard served by
`npm run preview`, demo mode, a fresh browser context each time (no cache),
Chromium, Linux build container, 2026-10-02. Time from navigation to the first
issue row on the radar page: 193, 214, 199, 158 and 191 ms. The `load` event
fired at 54 ms. With a real database the API adds its own time; the ranking
behind it is the one measured in M3 (about 2 s for 5,000 issues).

**Accessibility.** `npm run e2e` runs axe (WCAG 2.0 A and AA, 2.1 AA) on all
seven screens in light and dark themes, on a desktop and a phone viewport:
0 serious or critical violations. The first run found one (the Insights chart
was inside an `aria-hidden` region but contained a focusable element); it was
fixed by labelling the chart as a figure instead of hiding it.

**Keyboard.** The same suite runs the main flow by keyboard alone: `/` to
search, `j` to move, `o` to open the drawer, `Escape` to close it, `x` to
dismiss, `Ctrl+K` to jump to another page.

**Phone width.** No horizontal scrolling on any screen at 412 px (Pixel 7 viewport).

## M6: container image

Built from the `Dockerfile` in this repo, Linux build container, 2026-10-02.

- **Size:** 289 MB on disk, 68.1 MB compressed (`docker images`). Base
  `python:3.13-slim` is 190 MB of that.
- **Start to healthy:** 1,944, 2,461 and 2,038 ms from `docker run` to the
  first `200` from `/api/health` (`firstpr serve --demo`).
- **Daily job in the container:** `firstpr daily` synced, wrote
  `digests/latest.md` and `feed.xml`, and exited 0. PR search could not be
  checked here because the build sandbox blocks the search API; the CI
  self-test covers it.

## M6: what GITHUB_TOKEN can read

Measured by the `Action self-test` workflow, run
[37024126453](https://github.com/MuskanScripts/IssueRadar/actions/runs/37024126453),
2026-10-02, with only the built-in `GITHUB_TOKEN` (job permission
`contents: read`).

- **Other public repos: readable.** It synced
  `modelcontextprotocol/python-sdk` (245 open issues, 190 open PRs, 30
  finalists enriched with comments and timelines, health 51) as well as its
  own repo.
- **Search: works.** The `linked:pr` searches and the PR search
  `is:pr author:MuskanScripts` both answered, and the PR search found PRs in
  repos outside this one.
- **Limits it reported:** core 5,000 per hour, search 30 per minute. GitHub
  documents 1,000 requests per hour per repository for `GITHUB_TOKEN`; this
  run saw 5,000, so `firstpr doctor` reports the real numbers from
  `/rate_limit` rather than trusting either.
- **Cost of a cold run:** 83 requests for the sync and 38 for 10 PRs. The
  `firstpr daily` step took 47 seconds and the whole job 72 seconds. The saved
  database was 1.7 MB.
- **Digest:** 22 free issues, written to `latest.md` and `feed.xml` and
  uploaded as the `firstpr-digest` artifact.

So the template works with no secret at all for a small watchlist. A
fine-grained token is still recommended for larger ones (ADR 0006), mainly
for the search budget and because the `GITHUB_TOKEN` limit is not
guaranteed.

The same run showed the digest repeating a PR's status ("Merged. Merged.
Nothing to do."); fixed in the next commit with a test.

## M6: clean-machine setup time

Not measured yet. Target: under 10 minutes from the README alone on a Windows
machine with only Python installed (docs/human-tasks.md).

## M4: PR statuses compared with github.com

**Done when:** statuses match what github.com shows for at least 5 real PRs.

**Recorded check.** `tests/test_prs.py::test_status_matches_github_for_real_prs`
runs the tracker on five PRs recorded on 2026-10-02 with
`python scripts/record_fixtures.py --pr MuskanScripts/IssueRadar#<n>`:

| PR | What github.com showed | Tracker |
| --- | --- | --- |
| #2 | Merged | Merged |
| #12 (Dependabot) | Closed without merging; one check had failed | Closed unmerged (not "CI failing", because it is closed) |
| #14 | Merged | Merged |
| #15 | Merged | Merged |
| #16 | Open, six checks green, no reviews, opened that day | Waiting for review |

**Live check.** `firstpr prs --repo MuskanScripts/IssueRadar --author
MuskanScripts` on 2026-10-02 (18 requests; a second run answered all 18 with
304) listed #16 waiting for review, #15, #14 and #2 merged, and #1 closed
unmerged, matching GitHub for all six of the owner's PRs.

**Frozen time.** Stale-day logic is tested at 6, 7 and 30 days of quiet with a
fixed clock, and checks that the author's own commits don't reset it.

## M2: things noticed on real data

Measured on MuskanScripts/IssueRadar on 2026-10-02 (`firstpr watch add
MuskanScripts/IssueRadar`, `firstpr sync`), through the build container's
GitHub access:

- **Issue forms are invisible to the community profile.**
  `GET /repos/{o}/{r}/community/profile` reported `issue_template: null` for a
  repo with three YAML issue forms in `.github/ISSUE_TEMPLATE/`. IssueRadar now
  checks that folder when the profile says no. Health went from 67 to 70 for
  that repo once the forms were counted.
- **Repo health on a brand-new repo is mostly "not enough data".** With no
  outside PRs and no issues yet, two of five parts are unknown and scored 0.5.
  The reasons say so instead of guessing.

