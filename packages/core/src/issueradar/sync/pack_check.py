"""Check repos before recommending them in a starter pack (`firstpr pack verify`).

For each repo: is it active, does it have a CONTRIBUTING file, and how many of
its recently closed outside pull requests were accepted. Accepted means merged,
or imported by a bot per the repo's rules, the same way repo health counts it.
Only reads.
"""

from __future__ import annotations

from dataclasses import dataclass

from issueradar.config.settings import Settings
from issueradar.engine.health import outside_pr_outcome
from issueradar.engine.rules import RepoRules, rules_for
from issueradar.github.client import GitHubClient
from issueradar.github.errors import GitHubError, QuotaExhausted


@dataclass(frozen=True)
class RepoCheck:
    repo: str
    error: str | None = None
    archived: bool = False
    last_push: str = ""
    contributing: bool = False
    outside: int = 0
    accepted: int = 0
    imported: int = 0  # part of accepted: closed after a bot import, not merged

    @property
    def accepted_share(self) -> float | None:
        return self.accepted / self.outside if self.outside else None


async def check_repo(
    client: GitHubClient, repo: str, settings: Settings, rules: dict[str, RepoRules]
) -> RepoCheck:
    maintainers = {a.upper() for a in settings.availability.maintainer_associations}
    try:
        data = (await client.get(f"/repos/{repo}")).data
        community = (await client.get(f"/repos/{repo}/community/profile")).data or {}
        closed = (
            await client.get(
                f"/repos/{repo}/pulls",
                params={"state": "closed", "per_page": 100, "sort": "updated", "direction": "desc"},
            )
        ).data or []
    except QuotaExhausted:
        raise
    except GitHubError as exc:
        return RepoCheck(repo=repo, error=str(exc))

    repo_rules = rules_for(rules, repo)
    outcomes = [
        outside_pr_outcome(
            merged=bool(pr.get("merged_at")),
            labels=[lbl.get("name", "") for lbl in pr.get("labels") or [] if isinstance(lbl, dict)],
            rules=repo_rules,
        )
        for pr in closed
        if (pr.get("author_association") or "").upper() not in maintainers
        and (pr.get("user") or {}).get("type") != "Bot"
    ]
    return RepoCheck(
        repo=repo,
        archived=bool(data.get("archived")),
        last_push=(data.get("pushed_at") or "")[:10],
        contributing=bool((community.get("files") or {}).get("contributing")),
        outside=len(outcomes),
        accepted=sum(1 for o in outcomes if o != "closed"),
        imported=outcomes.count("accepted_by_bot"),
    )
