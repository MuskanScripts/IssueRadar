# Things only the maintainer can do

Keep this list current. Tick items when done.

## Now (M0 to M1)

- [ ] **Enable GitHub Actions** on `MuskanScripts/IssueRadar` (Settings, Actions, General) so CI runs.
- [ ] **Merge the M0 branch** into `main` after review.
- [ ] **Create a read-only token** for M1 (steps below) and keep it out of the repository.
- [ ] **Edit `examples/skills.yaml`** to match your real skills, then copy it to `skills.yaml`.
- [ ] **Choose delivery channels** for the digest (RSS and Markdown come first; then email, Telegram, Discord or Slack).

### Create the least-privileged token

1. On GitHub: your avatar, **Settings**, **Developer settings**, **Personal access tokens**, **Fine-grained tokens**, **Generate new token**.
2. Name it `firstpr-read-only`. Pick an expiry (90 days is a sensible default).
3. **Resource owner:** yourself.
4. **Repository access:** **Public repositories (read-only)**.
5. **Permissions:** leave everything at "No access". Fine-grained tokens always include read-only access to public repositories.
6. Generate, copy the token, and store it in your user environment, not in a file in the repo:

```powershell
[Environment]::SetEnvironmentVariable("FIRSTPR_GITHUB_TOKEN", "paste-token-here", "User")
```

Open a new PowerShell window afterwards so the variable is loaded, then run
`firstpr doctor`. (From M4 on, `doctor` also checks whether this token can list
your own pull requests; if it cannot, the notes will say what to change.)

## Later

- [ ] Register the OAuth app or GitHub App (M7).
- [ ] Set up PyPI and a trusted publisher for releases (M6).
- [ ] Check that the product name and domain are free to use.
- [ ] Hand-label at least 50 issues in the evaluation CSV (M2 ships the template).
- [ ] Record the demo screen recording (M6).
- [ ] Ask 5 people to try it.
- [ ] Enable GitHub Discussions.
- [ ] Have a lawyer review terms and privacy before hosted mode (M7).
