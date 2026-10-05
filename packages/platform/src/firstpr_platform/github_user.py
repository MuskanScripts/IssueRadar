"""GitHub calls made with one user's own token, on their behalf.

Reads (GET) can happen any time. Everything that changes something on GitHub
goes through `_write`, and only these methods call it: fork, sync the fork,
create a branch, create or delete a Codespace, open a pull request. Each of
them runs only because the user clicked a button (Start working, Create pull
request, Delete Codespace). Scheduled jobs only read; a test checks that.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

API_URL = "https://api.github.com"
# Every method that writes. Kept in one place so tests can name them.
WRITES = frozenset(
    {"fork", "sync_fork", "create_branch", "create_codespace", "delete_codespace", "create_pull"}
)
PR_TEMPLATES = (
    ".github/pull_request_template.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
    "pull_request_template.md",
    "PULL_REQUEST_TEMPLATE.md",
    "docs/pull_request_template.md",
)


class GitHubError(Exception):
    """GitHub refused. `status` is the HTTP status, `message` GitHub's own words."""

    def __init__(self, status: int, message: str, *, accepted: str | None = None) -> None:
        super().__init__(f"HTTP {status}: {message}")
        self.status = status
        self.message = message
        # x-accepted-github-permissions: what the app would need, when a permission is missing.
        self.accepted = accepted

    @property
    def not_installed(self) -> bool:
        """The app is not installed where this call needs it, or lacks a permission."""
        return self.status in (403, 404) and (
            "not accessible by integration" in self.message.lower() or self.accepted is not None
        )


@dataclass
class Compare:
    ahead_by: int
    commits: list[dict[str, Any]]
    files: list[dict[str, Any]]


class UserGitHub:
    def __init__(
        self,
        token: str,
        *,
        api_url: str = API_URL,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=api_url.rstrip("/"),
            transport=transport,
            timeout=30,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "FirstPR",
            },
        )

    async def __aenter__(self) -> UserGitHub:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._client.aclose()

    # ------------------------------------------------------------ plumbing

    @staticmethod
    def _error(resp: httpx.Response) -> GitHubError:
        try:
            body = resp.json()
            message = str(body.get("message") or resp.reason_phrase)
            errors = body.get("errors")
            if isinstance(errors, list) and errors:
                first = errors[0]
                detail = first.get("message") if isinstance(first, dict) else str(first)
                if detail:
                    message = f"{message}: {detail}"
        except ValueError:
            message = resp.reason_phrase
        return GitHubError(
            resp.status_code, message, accepted=resp.headers.get("x-accepted-github-permissions")
        )

    async def _get(self, path: str, **params: Any) -> Any:
        resp = await self._client.get(path, params=params or None)
        if resp.status_code >= 300:
            raise self._error(resp)
        return resp.json()

    async def _maybe(self, path: str, **params: Any) -> Any | None:
        resp = await self._client.get(path, params=params or None)
        if resp.status_code == 404:
            return None
        if resp.status_code >= 300:
            raise self._error(resp)
        return resp.json()

    async def _write(self, method: str, path: str, json: Any | None = None) -> Any:
        resp = await self._client.request(method, path, json=json)
        if resp.status_code >= 300:
            raise self._error(resp)
        return resp.json() if resp.content else None

    # --------------------------------------------------------------- reads

    async def login(self) -> str:
        return str((await self._get("/user"))["login"])

    async def app_installed(self, account: str) -> bool:
        """Whether the app this token belongs to is installed on `account`."""
        data = await self._get("/user/installations", per_page=100)
        return any(
            str(i.get("account", {}).get("login", "")).lower() == account.lower()
            for i in data.get("installations", [])
        )

    async def repo(self, full_name: str) -> dict[str, Any] | None:
        data: dict[str, Any] | None = await self._maybe(f"/repos/{full_name}")
        return data

    async def branch_sha(self, full_name: str, branch: str) -> str | None:
        data = await self._maybe(f"/repos/{full_name}/git/ref/heads/{quote(branch, safe='')}")
        return str(data["object"]["sha"]) if data else None

    async def codespace(self, name: str) -> dict[str, Any] | None:
        data: dict[str, Any] | None = await self._maybe(f"/user/codespaces/{name}")
        return data

    async def compare(self, full_name: str, base: str, head: str) -> Compare:
        data = await self._get(f"/repos/{full_name}/compare/{base}...{quote(head, safe='')}")
        return Compare(
            ahead_by=int(data.get("ahead_by") or 0),
            commits=list(data.get("commits") or []),
            files=list(data.get("files") or []),
        )

    async def pr_template(self, full_name: str) -> str | None:
        for path in PR_TEMPLATES:
            resp = await self._client.get(
                f"/repos/{full_name}/contents/{path}",
                headers={"Accept": "application/vnd.github.raw+json"},
            )
            if resp.status_code == 200:
                return resp.text
        return None

    async def open_pull(self, upstream: str, head: str) -> dict[str, Any] | None:
        """An open pull request from `head` (owner:branch) into upstream, if there is one."""
        pulls = await self._get(f"/repos/{upstream}/pulls", head=head, state="open")
        return pulls[0] if pulls else None

    # -------------------------------------------------------------- writes

    async def fork(self, upstream: str) -> dict[str, Any]:
        data: dict[str, Any] = await self._write(
            "POST", f"/repos/{upstream}/forks", {"default_branch_only": True}
        )
        return data

    async def sync_fork(self, fork: str, branch: str) -> None:
        await self._write("POST", f"/repos/{fork}/merge-upstream", {"branch": branch})

    async def create_branch(self, fork: str, branch: str, sha: str) -> None:
        await self._write(
            "POST", f"/repos/{fork}/git/refs", {"ref": f"refs/heads/{branch}", "sha": sha}
        )

    async def create_codespace(self, fork: str, branch: str) -> dict[str, Any]:
        data: dict[str, Any] = await self._write(
            "POST",
            f"/repos/{fork}/codespaces",
            {
                "ref": branch,
                # GitHub stops it after 15 idle minutes and deletes it 7 days after
                # it stopped, so FirstPR never has to delete anything on its own.
                "idle_timeout_minutes": 15,
                "retention_period_minutes": 7 * 24 * 60,
            },
        )
        return data

    async def delete_codespace(self, name: str) -> None:
        await self._write("DELETE", f"/user/codespaces/{name}")

    async def create_pull(
        self, upstream: str, head: str, base: str, title: str, body: str, draft: bool
    ) -> dict[str, Any]:
        data: dict[str, Any] = await self._write(
            "POST",
            f"/repos/{upstream}/pulls",
            {"title": title, "body": body, "head": head, "base": base, "draft": draft},
        )
        return data
