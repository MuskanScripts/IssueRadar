# Things only the maintainer can do

Keep this list current. Tick items when done.

## Now (M0 to M1)

- [x] **Enable GitHub Actions** on `MuskanScripts/IssueRadar`.
- [x] **Merge the M0 branch** into `main` after review.
- [ ] **Create a read-only token** (steps below) and keep it out of the repository.
- [ ] **Run the M1 measurements with your own token** and add the rows to `RESULTS.md`:
  `firstpr doctor --measure-etag modelcontextprotocol/python-sdk`, then add about 25 repos with
  `firstpr watch add ...` and run `firstpr sync` twice.
- [ ] **Record a few more real fixtures** with `python scripts/record_fixtures.py owner/repo`
  (repos with real issues and human PRs), so M2 tests use more than one repo.
- [ ] **Verify the starter packs** with `firstpr pack verify <name>` for each pack and set
  `verified: true` in the pack file when every repo looks active and open to outside PRs.
- [ ] **Label at least 50 issues** with `firstpr eval sample` and `eval/README.md`, then run
  `firstpr eval run eval/labels.csv` and add the numbers to `RESULTS.md`.
- [ ] **Close Dependabot PRs #12 and #13** (React 19). The project is on React 18; Dependabot is
  now told to skip React major versions.
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

## M6 (distribution)

- [ ] **Create the template repo.** New repo `MuskanScripts/firstpr-radar-template`, copy
  everything in `template/` into it (including `.github/`), then **Settings > General >
  Template repository**. Run its workflow once by hand and check a digest appears.
- [ ] **Register the PyPI trusted publisher.** On pypi.org: **Your projects > Publishing >
  Add a new pending publisher**: project `firstpr`, owner `MuskanScripts`, repository
  `IssueRadar`, workflow `release.yml`, environment `pypi`. Then create the `pypi`
  environment in this repo (**Settings > Environments**).
- [ ] **Turn on GitHub Pages** with source **GitHub Actions** (**Settings > Pages**). The
  `Landing page` workflow deploys `site/` on the next push to `main`.
- [ ] **Make the first release.** Rename `## [Unreleased]` in CHANGELOG.md to
  `## [0.1.0] - <date>`, set `version = "0.1.0"` in `pyproject.toml`, merge, then:

  ```powershell
  git tag v0.1.0
  git push origin v0.1.0
  ```

  The release workflow publishes to PyPI and GHCR, creates the GitHub release and moves the
  `v0` tag the template uses. Afterwards make the GHCR package public (**Packages >
  issueradar > Package settings > Change visibility**).
- [ ] **Upload the social preview**: `site/social-preview.png` in **Settings > General >
  Social preview**.
- [ ] **Record the screen recording**: `firstpr serve --demo`, then the radar, an issue's
  reasons, My PRs and the digest preview, about 60 seconds. Put it in the README.
- [ ] **Clean-machine test.** On a Windows machine (or a fresh Windows Sandbox) with only
  Python installed, follow the README from the top and time it. Done when it takes under
  10 minutes. Note what was confusing.
- [ ] **Read the self-test result** (`Action self-test` workflow) and copy what `GITHUB_TOKEN`
  could read into RESULTS.md.

## Later

- [ ] Register the OAuth app or GitHub App (M7).
- [ ] Check that the product name and domain are free to use.
- [ ] Ask 5 people to try it.
- [ ] Enable GitHub Discussions.
- [ ] Have a lawyer review terms and privacy before hosted mode (M7).
