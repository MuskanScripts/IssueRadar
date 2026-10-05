# Step 0: checks before building the platform

Before any platform code, three things need answers. If one fails, the plan changes before we build on it.

1. GitHub App checks: can the app read public repos it is not installed on, and can a user token fork, branch, set a Codespaces secret and open a Codespace?
2. Engine check: on 50 hand-labelled issues, how often is an issue the engine calls free really free?
3. One manual run: from finding an issue to a merged PR, timed step by step.

## 1. GitHub App checks

### Create a throwaway app

On GitHub: Settings, Developer settings, GitHub Apps, New GitHub App.

| Field | Value |
|---|---|
| Name | anything unique, for example `firstpr-check-<yourname>` |
| Homepage URL | `https://muskanscripts.github.io/IssueRadar/` |
| Callback URL | leave empty |
| Enable Device Flow | ticked |
| Webhook, Active | unticked |
| Repository permissions | Administration: read and write; Codespaces: read and write; Contents: read and write; Issues: read; Metadata: read; Pull requests: read and write |
| Account permissions | Codespaces user secrets: read and write |
| Where can this app be installed | Only on this account |

Then:

1. Create the app. Note the **App ID** and the **Client ID** at the top of its page.
2. Under Private keys, Generate a private key. A `.pem` file downloads. Keep it outside the repo.
3. Install App (left menu), choose your account, **All repositories**.

### Run the checks

```powershell
pip install "pyjwt[crypto]" pynacl
$env:CHECK_APP_ID = "<App ID>"
$env:CHECK_APP_CLIENT_ID = "<Client ID>"
$env:CHECK_APP_KEY = "C:\keys\firstpr-check.private-key.pem"
python scripts/github_app_checks.py
```

It asks you to open a GitHub page and enter a code once (that is your user token). Then it forks `octocat/Spoon-Knife`, makes a branch, sets a Codespaces secret, opens a Codespace and waits until it is ready, then deletes the branch, Codespace and secret again. The Codespace runs for two or three minutes on your own free hours. The fork stays; delete it afterwards.

Add `--skip-codespace` to run only the read, fork and branch checks.

The last lines print a PASS or FAIL summary with the reason for each check. When a check fails because of a permission, the reason includes the permission GitHub asked for.

When done, delete the app (its page, Advanced, Delete) and the `.pem` file.

## 2. Engine check

```powershell
firstpr sync
firstpr eval sample --out eval/labels.csv --per-repo 6
```

Label each row as described in `eval/README.md`, then:

```powershell
firstpr eval run eval/labels.csv --json eval/results.json
```

Gate: FREE precision (strict) of at least 80%.

## 3. Manual run

Pick a beginner issue on a practice repo, then fork, open a Codespace, change, push, open the PR and get it merged. Write down how long each step took.

## Results

| Check | Result | Notes |
|---|---|---|
| A1 installation token reads a public repo | | |
| A2 304 does not count | | |
| B1 to B4 user token, fork, branch | | |
| C1 to C5 Codespaces secret and Codespace | | |
| FREE precision (strict) | | |
| Manual run, issue to PR | | |
