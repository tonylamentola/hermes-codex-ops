# GitHub Workflow

GitHub is source of truth for repositories and reviewable code history.

## Rules

- Never allow uncontrolled commits.
- Require explicit commit summaries before committing.
- Log all GitHub actions.
- Summarize commits, diffs, branches, and deployments into memory.
- Store local checkouts under `/repos`.

## Configuration

Use `.env` for secrets:

```bash
GITHUB_TOKEN=
GITHUB_OWNER=
```

Use `config/repos.example.json` as the shape for tracked repositories, then create `config/repos.json`. The local `config/repos.json` file is intentionally gitignored so each VPS/operator can choose the repos to monitor.

```json
{
  "repositories": [
    {
      "owner": "example-owner",
      "name": "example-repo",
      "default_branch": "main",
      "deployment_provider": "manual",
      "deployment_url": "https://example.com",
      "healthcheck_url": "https://example.com/health"
    }
  ]
}
```

The GitHub watcher reads this file, fetches repository metadata, branch state, and recent commits, then writes:

- `memory/github-state.md`
- `memory/github-state.json`

It never commits, pushes, or mutates repository state.

## Recovery

```bash
less memory/github-state.md
jq . config/repos.json
jq . memory/github-state.json
git -C repos/example-repo status
```
