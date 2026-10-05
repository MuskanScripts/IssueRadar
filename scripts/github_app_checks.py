"""Step 0 checks: can a GitHub App do what the FirstPR platform needs?

Answers three questions before any platform code is written:

  A. Can the app's installation token read a public repo where the app is
     not installed, and do unchanged answers (304) leave the limit alone?
  B. Can a user token from the app fork a repo and create a branch?
  C. Can that user token set a Codespaces secret for the fork and open a
     Codespace with a 15-minute idle timeout?

Unlike the rest of this project, check B and C write to GitHub, but only to
your own account: a fork of octocat/Spoon-Knife (GitHub's practice repo), a
branch on it, a Codespaces secret and a Codespace. The branch, secret and
Codespace are deleted again at the end; the fork stays (delete it by hand).
Tokens are kept in memory only and never printed or written to disk.

Usage (PowerShell, from the repository root, virtual environment active):

    pip install "pyjwt[crypto]" pynacl
    $env:CHECK_APP_ID = "123456"
    $env:CHECK_APP_CLIENT_ID = "Iv23li..."
    $env:CHECK_APP_KEY = "C:\\keys\\firstpr-check.private-key.pem"
    python scripts/github_app_checks.py
    python scripts/github_app_checks.py --skip-codespace   # A and B only
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

API = "https://api.github.com"
PUBLIC_REPO = "pallets/flask"  # read with the installation token; the app is not installed there
PRACTICE_REPO = "octocat/Spoon-Knife"
SECRET_NAME = "FIRSTPR_WORKSPACE_KEY"  # noqa: S105 - a secret name, not a value
HEADERS = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}


@dataclass
class Report:
    rows: list[tuple[str, bool, str]] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str) -> bool:
        self.rows.append((name, ok, detail))
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
        return ok

    def summary(self) -> int:
        print("\nSummary (paste this back):")
        for name, ok, detail in self.rows:
            print(f"- {'PASS' if ok else 'FAIL'} | {name} | {detail}")
        return 0 if all(ok for _, ok, _ in self.rows) else 1


def need_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(f"Set ${name} first (see the top of this file).")
    return value


def why(resp: httpx.Response) -> str:
    try:
        message = resp.json().get("message", "")
    except ValueError:
        message = resp.text[:120]
    accepted = resp.headers.get("x-accepted-github-permissions")
    extra = f"; needs {accepted}" if accepted else ""
    return f"HTTP {resp.status_code} {message}{extra}"


def app_jwt(app_id: str, key_path: str) -> str:
    import jwt  # pyjwt[crypto]

    now = int(time.time())
    key = Path(key_path).read_text(encoding="utf-8")
    return jwt.encode({"iat": now - 60, "exp": now + 540, "iss": app_id}, key, algorithm="RS256")


def installation_token(client: httpx.Client, app_id: str, key_path: str) -> tuple[str, str]:
    auth = {"Authorization": f"Bearer {app_jwt(app_id, key_path)}"}
    resp = client.get("/app/installations", headers=auth)
    resp.raise_for_status()
    installs = resp.json()
    if not installs:
        sys.exit("The app has no installations. Install it on your account first.")
    install = installs[0]
    resp = client.post(f"/app/installations/{install['id']}/access_tokens", headers=auth)
    resp.raise_for_status()
    return resp.json()["token"], install["account"]["login"]


def device_flow_token(client_id: str) -> str:
    with httpx.Client(headers={"Accept": "application/json"}, timeout=30) as gh:
        start = gh.post("https://github.com/login/device/code", data={"client_id": client_id})
        start.raise_for_status()
        info = start.json()
        if "user_code" not in info:
            sys.exit(f"Device flow refused: {info}. Is 'Enable Device Flow' ticked on the app?")
        print(f"\n  Open {info['verification_uri']} and enter the code {info['user_code']}")
        print("  (waiting for you to approve in the browser...)")
        interval = int(info.get("interval", 5))
        deadline = time.time() + int(info.get("expires_in", 900))
        while time.time() < deadline:
            time.sleep(interval)
            poll = gh.post(
                "https://github.com/login/oauth/access_token",
                data={
                    "client_id": client_id,
                    "device_code": info["device_code"],
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
            ).json()
            if "access_token" in poll:
                return str(poll["access_token"])
            if poll.get("error") == "slow_down":
                interval += 5
            elif poll.get("error") != "authorization_pending":
                sys.exit(f"Sign-in failed: {poll.get('error_description', poll)}")
    sys.exit("The code expired before it was approved.")


def check_installation(report: Report, client: httpx.Client, token: str) -> None:
    print(f"\nA. Installation token reading {PUBLIC_REPO} (app not installed there)")
    auth = {"Authorization": f"Bearer {token}"}
    url = f"/repos/{PUBLIC_REPO}/issues"
    first = client.get(url, params={"per_page": 1}, headers=auth)
    if not report.add(
        "A1 read public repo",
        first.status_code == 200,
        why(first)
        if first.status_code != 200
        else f"limit {first.headers.get('x-ratelimit-limit')} an hour "
        f"({first.headers.get('x-ratelimit-resource')})",
    ):
        return
    used_before = int(first.headers.get("x-ratelimit-used", "0"))
    again = client.get(
        url,
        params={"per_page": 1},
        headers={**auth, "If-None-Match": first.headers.get("etag", "")},
    )
    used_after = int(again.headers.get("x-ratelimit-used", "0"))
    report.add(
        "A2 ETag 304 is free",
        again.status_code == 304 and used_after == used_before,
        f"HTTP {again.status_code}, requests used {used_before} -> {used_after}",
    )


def wait_for(client: httpx.Client, url: str, auth: dict[str, str], seconds: int) -> httpx.Response:
    deadline = time.time() + seconds
    resp = client.get(url, headers=auth)
    while resp.status_code == 404 and time.time() < deadline:
        time.sleep(3)
        resp = client.get(url, headers=auth)
    return resp


def check_user(report: Report, client: httpx.Client, token: str, codespace: bool) -> None:
    auth = {"Authorization": f"Bearer {token}"}
    me = client.get("/user", headers=auth)
    if not report.add(
        "B1 user token works",
        me.status_code == 200,
        f"signed in as {me.json().get('login')}" if me.status_code == 200 else why(me),
    ):
        return
    login = me.json()["login"]
    name = PRACTICE_REPO.split("/")[1]

    print(f"\nB. Fork {PRACTICE_REPO} and create a branch, with the user token")
    fork = client.post(f"/repos/{PRACTICE_REPO}/forks", headers=auth)
    if not report.add(
        "B2 fork",
        fork.status_code in (200, 202),
        why(fork) if fork.status_code >= 300 else f"{login}/{name}",
    ):
        return
    repo = wait_for(client, f"/repos/{login}/{name}", auth, 60)
    if not report.add(
        "B3 fork ready",
        repo.status_code == 200,
        why(repo) if repo.status_code != 200 else "visible within a minute",
    ):
        return
    fork_id, default = repo.json()["id"], repo.json()["default_branch"]
    head = client.get(f"/repos/{login}/{name}/git/ref/heads/{default}", headers=auth)
    branch = f"firstpr-check-{int(time.time())}"
    made = client.post(
        f"/repos/{login}/{name}/git/refs",
        headers=auth,
        json={"ref": f"refs/heads/{branch}", "sha": head.json().get("object", {}).get("sha")},
    )
    if not report.add(
        "B4 create branch",
        made.status_code == 201,
        why(made) if made.status_code != 201 else branch,
    ):
        return

    try:
        if codespace:
            check_codespace(report, client, auth, login, name, fork_id, branch)
    finally:
        gone = client.delete(f"/repos/{login}/{name}/git/refs/heads/{branch}", headers=auth)
        print(f"  (cleanup: branch deleted: {gone.status_code == 204})")


def check_codespace(
    report: Report,
    client: httpx.Client,
    auth: dict[str, str],
    login: str,
    name: str,
    fork_id: int,
    branch: str,
) -> None:
    from nacl import encoding, public  # pynacl

    print("\nC. Codespaces secret and a Codespace with a 15-minute idle timeout")
    key = client.get("/user/codespaces/secrets/public-key", headers=auth)
    secret_set = False
    if report.add(
        "C1 read secrets key", key.status_code == 200, why(key) if key.status_code != 200 else "ok"
    ):
        box = public.SealedBox(public.PublicKey(key.json()["key"].encode(), encoding.Base64Encoder))
        sealed = base64.b64encode(box.encrypt(os.urandom(24).hex().encode())).decode()
        put = client.put(
            f"/user/codespaces/secrets/{SECRET_NAME}",
            headers=auth,
            json={
                "encrypted_value": sealed,
                "key_id": key.json()["key_id"],
                "selected_repository_ids": [fork_id],
            },
        )
        secret_set = report.add(
            "C2 set secret for the fork",
            put.status_code in (201, 204),
            why(put) if put.status_code >= 300 else f"{SECRET_NAME} on {login}/{name}",
        )

    made = client.post(
        f"/repos/{login}/{name}/codespaces",
        headers=auth,
        json={"ref": branch, "idle_timeout_minutes": 15},
    )
    cs: dict[str, Any] = made.json() if made.status_code in (201, 202) else {}
    if report.add("C3 create Codespace", bool(cs), why(made) if not cs else cs.get("name", "")):
        report.add(
            "C4 idle timeout is 15",
            cs.get("idle_timeout_minutes") == 15,
            f"GitHub reports {cs.get('idle_timeout_minutes')} minutes",
        )
        state, deadline = cs.get("state"), time.time() + 180
        while state not in ("Available", "Failed") and time.time() < deadline:
            time.sleep(10)
            got = client.get(f"/user/codespaces/{cs['name']}", headers=auth)
            state = got.json().get("state") if got.status_code == 200 else f"HTTP {got.status_code}"
        report.add("C5 read Codespace state", state == "Available", f"last state: {state}")
        gone = client.delete(f"/user/codespaces/{cs['name']}", headers=auth)
        print(f"  (cleanup: Codespace deleted: {gone.status_code in (202, 204)})")
    if secret_set:
        gone = client.delete(f"/user/codespaces/secrets/{SECRET_NAME}", headers=auth)
        print(f"  (cleanup: secret deleted: {gone.status_code == 204})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skip-codespace", action="store_true", help="run A and B only")
    args = parser.parse_args()
    app_id, client_id, key_path = (
        need_env("CHECK_APP_ID"),
        need_env("CHECK_APP_CLIENT_ID"),
        need_env("CHECK_APP_KEY"),
    )

    report = Report()
    with httpx.Client(base_url=API, headers=HEADERS, timeout=30) as client:
        token, account = installation_token(client, app_id, key_path)
        print(f"Installation found on {account}.")
        check_installation(report, client, token)
        print("\nSign in as yourself through the app (device flow):")
        check_user(report, client, device_flow_token(client_id), codespace=not args.skip_codespace)
    fork_name = PRACTICE_REPO.split("/")[1]
    print(f"\nThe fork {fork_name} stays on your account; delete it on GitHub when done.")
    return report.summary()


if __name__ == "__main__":
    raise SystemExit(main())
