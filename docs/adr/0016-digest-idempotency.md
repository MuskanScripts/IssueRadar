# 0016. A digest item is sent once, until what the reader sees changes

- Status: accepted
- Date: 2026-10-02

## Context

The brief asks for an idempotent digest: the same issue is not repeated unless
its state changed, with dismiss and snooze, and a friendly quiet-day message.
"Running it twice sends nothing new the second time."

## Decision

- Each item has a key (`issue:owner/repo#12`, `pr:...`, `repo:...`) and a hash
  of what the reader sees: availability, tier and title for issues; status for
  pull requests.
- `seen_items` stores the hash of every item that was actually delivered. An
  item is included again only when its hash differs.
- Dismissed items never come back. Snoozed items come back after their date.
- The quiet-day message is included only when there is nothing new and no
  digest was sent earlier that day. So a second run on the same day sends
  nothing at all, and a quiet day still gets one short note.
- `firstpr digest` without `--send` is a preview and records nothing.

## Consequences

A rank change alone does not resend an issue; a change of state does. If every
channel fails, nothing is marked as sent, so the next run tries again.
