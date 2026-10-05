"""Evaluation harness (brief 11): how often are FREE and the tier right?

You label real issues in a CSV (``eval/labels_template.csv``); this module
compares the engines' answers with your labels and reports:

* FREE detection: precision and recall, counted two ways. "strict" treats only
  FREE as a positive prediction; "lenient" also counts LIKELY_FREE.
* Tier accuracy: exact matches, matches within one tier, and a confusion table.

Only rows with a label are scored. Issues that are not in the database are
skipped and counted, so the numbers never include guesses.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from sqlalchemy import select

from issueradar.models import Availability, Tier
from issueradar.radar import Radar
from issueradar.storage.models import Issue, Repo
from issueradar.sync.single import IssueUrlError, parse_issue_ref

COLUMNS = ["issue_url", "title", "truly_free", "tier", "notes", "labelled_by", "labelled_on"]
YES = {"yes", "y", "true", "1", "free"}
NO = {"no", "n", "false", "0", "taken", "not free"}
TIERS = {t.value: t for t in Tier}


@dataclass
class BinaryScore:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0

    @property
    def precision(self) -> float | None:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else None

    @property
    def recall(self) -> float | None:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else None

    def add(self, predicted: bool, actual: bool) -> None:
        if predicted and actual:
            self.tp += 1
        elif predicted:
            self.fp += 1
        elif actual:
            self.fn += 1
        else:
            self.tn += 1


@dataclass
class EvalReport:
    rows: int = 0
    labelled_free: int = 0
    labelled_tier: int = 0
    missing: list[str] = field(default_factory=list)
    bad_rows: list[str] = field(default_factory=list)
    strict: BinaryScore = field(default_factory=BinaryScore)
    lenient: BinaryScore = field(default_factory=BinaryScore)
    tier_exact: int = 0
    tier_within_one: int = 0
    tier_confusion: dict[str, dict[str, int]] = field(default_factory=dict)
    predicted_states: dict[str, int] = field(default_factory=dict)

    @property
    def tier_accuracy(self) -> float | None:
        return self.tier_exact / self.labelled_tier if self.labelled_tier else None

    def to_json(self) -> str:
        data = asdict(self)
        for name in ("strict", "lenient"):
            score: BinaryScore = getattr(self, name)
            data[name].update(precision=score.precision, recall=score.recall)
        data["tier_accuracy"] = self.tier_accuracy
        return json.dumps(data, indent=2)


def _parse_free(value: str) -> bool | None:
    text = value.strip().lower()
    if text in YES:
        return True
    if text in NO:
        return False
    return None


def run(radar: Radar, labels: Path) -> EvalReport:
    report = EvalReport()
    states: Counter[str] = Counter()
    order = [Tier.BEGINNER, Tier.INTERMEDIATE, Tier.PRO]
    confusion = {a.value: {p.value: 0 for p in order} for a in order}
    with labels.open(newline="", encoding="utf-8-sig") as handle:
        for line, row in enumerate(csv.DictReader(handle), start=2):
            url = (row.get("issue_url") or "").strip()
            if not url:
                continue
            truth_free = _parse_free(row.get("truly_free") or "")
            truth_tier = TIERS.get((row.get("tier") or "").strip().lower())
            if truth_free is None and truth_tier is None:
                continue  # not labelled yet
            report.rows += 1
            try:
                repo, number = parse_issue_ref(url)
            except IssueUrlError:
                report.bad_rows.append(f"line {line}: {url}")
                continue
            result = radar.report_for(repo, number)
            if result is None:
                report.missing.append(url)
                continue
            state = result.availability.state
            states[state.value] += 1
            if truth_free is not None:
                report.labelled_free += 1
                report.strict.add(state is Availability.FREE, truth_free)
                report.lenient.add(state.rankable, truth_free)
            if truth_tier is not None:
                report.labelled_tier += 1
                predicted = result.difficulty.tier
                confusion[truth_tier.value][predicted.value] += 1
                gap = abs(order.index(predicted) - order.index(truth_tier))
                report.tier_exact += gap == 0
                report.tier_within_one += gap <= 1
    report.tier_confusion = confusion
    report.predicted_states = dict(states)
    return report


def sample(radar: Radar, out: Path, *, per_repo: int, repos: list[str] | None = None) -> int:
    """Write a labelling sheet with open issues from the database. No predictions in it,
    so they can't bias the labels."""
    rows = []
    with radar.db.sessions() as session:
        query = select(Repo).order_by(Repo.full_name)
        if repos:
            query = query.where(Repo.full_name.in_(repos))
        for repo in session.scalars(query):
            issues = session.scalars(
                select(Issue)
                .where(Issue.repo_id == repo.id, Issue.state == "open")
                .order_by(Issue.gh_updated_at.desc())
                .limit(per_repo)
            )
            for issue in issues:
                rows.append({"issue_url": issue.html_url, "title": issue.title})
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return len(rows)
