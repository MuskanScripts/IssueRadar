"""A small fake of GitHub's REST API for the workspace flow.

Shared by the platform, API and worker tests. Every request is recorded, so a
test can check which calls wrote to GitHub.
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import parse_qs, unquote

import httpx

API = "https://api.github.com"


class FakeUserGitHub:
    def __init__(self, login: str = "MuskanScripts") -> None:
        self.login = login
        self.installed = True
        self.calls: list[tuple[str, str]] = []
        self.repos: dict[str, dict[str, Any]] = {}
        self.branches: dict[str, dict[str, str]] = {}  # repo -> branch -> sha
        self.codespaces: dict[str, dict[str, Any]] = {}
        self.codespace_error: tuple[int, str] | None = None
        self.codespace_state = "Available"
        self.sync_conflict = False
        self.ahead_by = 0
        self.template: str | None = None
        self.pulls: list[dict[str, Any]] = []
        self.pull_error: tuple[int, str] | None = None
        self.fork_visible = True

    def upstream(self, full_name: str, default_branch: str = "main") -> None:
        self.repos[full_name.lower()] = {
            "full_name": full_name,
            "default_branch": default_branch,
            "fork": False,
            "private": False,
        }
        self.branches[full_name.lower()] = {default_branch: "a" * 40}

    @property
    def writes(self) -> list[tuple[str, str]]:
        return [c for c in self.calls if c[0] != "GET"]

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)

    def handler(self, request: httpx.Request) -> httpx.Response:
        method = request.method
        path = unquote(request.url.path)
        self.calls.append((method, path))
        body = json.loads(request.content) if request.content else {}

        if path == "/user/installations":
            account = {"login": self.login}
            return httpx.Response(
                200, json={"installations": [{"account": account}] if self.installed else []}
            )
        match = re.fullmatch(r"/user/codespaces/([^/]+)", path)
        if match:
            space = self.codespaces.get(match.group(1))
            if space is None:
                return httpx.Response(404, json={"message": "Not Found"})
            if method == "DELETE":
                del self.codespaces[match.group(1)]
                return httpx.Response(202, json={})
            return httpx.Response(200, json={**space, "state": self.codespace_state})

        match = re.fullmatch(r"/repos/([^/]+/[^/]+)(/.*)?", path)
        if not match:
            return httpx.Response(404, json={"message": "Not Found"})
        repo, rest = match.group(1).lower(), match.group(2) or ""

        if rest == "" and method == "GET":
            data = self.repos.get(repo)
            if data is None or (data.get("fork") and not self.fork_visible):
                return httpx.Response(404, json={"message": "Not Found"})
            return httpx.Response(200, json=data)
        if rest == "/forks" and method == "POST":
            up = self.repos[repo]
            name = f"{self.login}/{up['full_name'].split('/')[1]}"
            self.repos[name.lower()] = {
                "full_name": name,
                "default_branch": up["default_branch"],
                "fork": True,
                "parent": {"full_name": up["full_name"]},
            }
            self.branches[name.lower()] = {up["default_branch"]: "b" * 40}
            return httpx.Response(202, json=self.repos[name.lower()])
        if rest == "/merge-upstream" and method == "POST":
            if self.sync_conflict:
                return httpx.Response(409, json={"message": "Merge conflict"})
            parent = self.repos[repo]["parent"]["full_name"].lower()
            branch = body["branch"]
            self.branches[repo][branch] = self.branches[parent][branch]
            return httpx.Response(200, json={"merge_type": "fast-forward"})
        match = re.fullmatch(r"/git/ref/heads/(.+)", rest)
        if match and method == "GET":
            sha = self.branches.get(repo, {}).get(match.group(1))
            if sha is None:
                return httpx.Response(404, json={"message": "Not Found"})
            return httpx.Response(200, json={"object": {"sha": sha}})
        if rest == "/git/refs" and method == "POST":
            self.branches[repo][body["ref"].removeprefix("refs/heads/")] = body["sha"]
            return httpx.Response(201, json={})
        if rest == "/codespaces" and method == "POST":
            if self.codespace_error:
                status, message = self.codespace_error
                return httpx.Response(status, json={"message": message})
            name = f"cs-{len(self.codespaces) + 1}"
            self.codespaces[name] = {
                "name": name,
                "web_url": f"https://{name}.github.dev",
                "state": "Queued",
                "idle_timeout_minutes": body.get("idle_timeout_minutes"),
                "retention_period_minutes": body.get("retention_period_minutes"),
            }
            return httpx.Response(201, json=self.codespaces[name])
        if rest.startswith("/compare/") and method == "GET":
            commits = [
                {"sha": f"{i:040d}", "commit": {"message": f"Change {i}\n\ndetails"}}
                for i in range(1, self.ahead_by + 1)
            ]
            files = [
                {"filename": "docs/a.md", "status": "modified", "additions": 3, "deletions": 1}
            ]
            return httpx.Response(
                200,
                json={
                    "ahead_by": self.ahead_by,
                    "commits": commits,
                    "files": files if commits else [],
                },
            )
        if rest.startswith("/contents/") and method == "GET":
            if self.template and rest == "/contents/.github/pull_request_template.md":
                return httpx.Response(200, text=self.template)
            return httpx.Response(404, json={"message": "Not Found"})
        if rest == "/pulls" and method == "GET":
            head = parse_qs(request.url.query.decode()).get("head", [""])[0]
            return httpx.Response(200, json=[p for p in self.pulls if p["head"] == head])
        if rest == "/pulls" and method == "POST":
            if self.pull_error:
                status, message = self.pull_error
                return httpx.Response(status, json={"message": message})
            number = 100 + len(self.pulls)
            pull = {
                "number": number,
                "html_url": f"https://github.com/{self.repos[repo]['full_name']}/pull/{number}",
                "draft": body.get("draft", False),
                "head": body["head"],
                "title": body["title"],
                "body": body["body"],
            }
            self.pulls.append(pull)
            return httpx.Response(201, json=pull)
        return httpx.Response(404, json={"message": "Not Found"})
