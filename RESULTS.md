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

