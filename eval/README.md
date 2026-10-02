# Evaluation set

`firstpr eval` measures how often the engines agree with a person. The numbers
in RESULTS.md come only from issues a person labelled by hand.

## Make a labelling sheet

Sync some repos first, then write a sheet of their open issues:

```powershell
firstpr eval sample --out eval/labels.csv --per-repo 10
```

The sheet has no predictions in it, so they can't sway you.

## Label

For each row, open the issue on GitHub and fill in:

| Column | Values | Meaning |
| --- | --- | --- |
| `truly_free` | `yes` / `no` | Could a newcomer start on it today without stepping on anyone? Look at assignees, linked PRs, and comments. |
| `tier` | `beginner` / `intermediate` / `pro` | How hard is it for someone new to this repo? |
| `notes` | text | Anything that made it hard to decide. |
| `labelled_by`, `labelled_on` | your name, date | So results can be traced. |

Leave a cell empty if you can't tell. A row with neither column filled is skipped.

## Score

```powershell
firstpr eval run eval/labels.csv
```

It prints precision and recall for FREE detection (strict: only FREE counts as
"free"; lenient: FREE or LIKELY_FREE) and tier accuracy. Copy the output and the
command into RESULTS.md. Issues missing from the database are skipped and
listed; run `firstpr explain <url>` on them first.

`labels_template.csv` shows the format. Keep your own sheet as
`eval/labels.csv` (it is committed, so results can be reproduced).
