# GitHub API fixtures

Tests never touch the network. They use these files, and each one says where
it came from in its `source` field.

| Folder | `source` | What it is |
| --- | --- | --- |
| `recorded/` | `recorded` | Real responses from api.github.com, recorded with `scripts/record_fixtures.py`. Only selected headers are kept and no token is ever written. |
| `examples/` | `github-openapi-example` | The example responses GitHub publishes in its OpenAPI description (`github/rest-api-description`). Documented shapes, not live data. |

GraphQL fixtures are written inline in the tests and follow the shapes in
GitHub's GraphQL docs, because GraphQL was not reachable from the environment
where M1 was built. Record real ones with a personal token before relying on
them.

## Recording more

With the virtual environment active and a token set:

```powershell
$env:FIRSTPR_GITHUB_TOKEN = "your-read-only-token"
python scripts/record_fixtures.py owner/repo
```

The recordings made on 2026-10-02 went through a build container whose proxy
added its own credentials, which is why their headers show a 15,000 per hour
limit.
