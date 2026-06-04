# Secrets

## What Can Be Read

Local `.env` values are read by Docker and Python services.

GitHub Actions secrets can be listed by name with `gh secret list`, but GitHub does not expose secret values after they are saved.

## Recommended VPS Setup

For the VPS, create `.env` directly on the server:

```bash
TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_CHAT_IDS=
GITHUB_TOKEN=
WORKER_BACKEND=codex-cli
WORKER_REQUIRE_APPROVAL=true
CODEX_CLI_MODEL=gpt-5.3-codex
CODEX_CLI_SANDBOX=read-only
```

Then run as root so Docker can mount the login directory into the worker and Telegram containers:

```bash
codex login
codex login status
cd /opt/hermes-codex-ops/system/docker
docker compose run --rm worker codex login status
```

The Codex login files live under `/root/.codex` and are mounted read-only into Codex-calling containers. Do not commit or copy those files into the repository.

## GitHub Secrets

Use GitHub secrets for GitHub Actions workflows. Do not depend on them as a recoverable secret store for the VPS because their values cannot be inspected later.
