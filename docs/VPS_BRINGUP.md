# VPS Bring-Up

This is the first live-run checklist for an Ubuntu VPS.

## 1. Copy or Clone

Put the project at:

```bash
/opt/hermes-codex-ops
```

## 2. Bootstrap

```bash
cd /opt/hermes-codex-ops
bash system/scripts/bootstrap_ubuntu.sh
```

The script installs system dependencies, creates `.env`, creates `config/repos.json`, creates `config/control-state.json`, installs Python dependencies, initializes memory/queue/logs, and writes the first context pack.

## 3. Configure Secrets

Edit `.env`:

```bash
OPENAI_API_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_CHAT_IDS=
GITHUB_TOKEN=
WORKER_BACKEND=dry-run
WORKER_REQUIRE_APPROVAL=true
```

Start live with `WORKER_BACKEND=dry-run` and `WORKER_REQUIRE_APPROVAL=true`.

To use a Codex subscription login instead of an OpenAI API key, install/sign in to Codex on the VPS and then use:

```bash
WORKER_BACKEND=codex-cli
CODEX_CLI_MODEL=gpt-5.3-codex
CODEX_CLI_SANDBOX=read-only
WORKER_REQUIRE_APPROVAL=true
```

Run this once as root on the VPS, then verify the Docker worker can see the same login:

```bash
codex login
codex login status
cd /opt/hermes-codex-ops/system/docker
docker compose run --rm worker codex login status
```

The Compose file mounts `/root/.codex` read-only into Codex-calling containers. If `codex login` was run as a non-root user, repeat it as root or update the mount intentionally.

GitHub repository secrets can be used by GitHub Actions, but their values cannot be read back by this platform. If a token only exists as a GitHub secret, either run the platform through a GitHub Actions workflow that injects the secret, or paste the token into the VPS `.env` manually.

## 4. Configure Repositories

Edit:

```bash
config/repos.json
```

Use `config/repos.example.json` as the shape.

## 5. Start Services

```bash
cd /opt/hermes-codex-ops/system/docker
docker compose up -d --build
docker compose ps
```

## 6. Health Check

```bash
cd /opt/hermes-codex-ops
source .venv/bin/activate
python -m system.scripts.healthcheck
tail -n 50 logs/ops.jsonl
sqlite3 tasks/queue.sqlite3 'select status,count(*) from tasks group by status;'
```

## 7. Live Smoke

```bash
cd /opt/hermes-codex-ops
APP_DIR=/opt/hermes-codex-ops bash system/scripts/live_smoke.sh
```

Telegram smoke:

```text
/status
/submit test from telegram
/tasks
/approve TASK_ID
/status
```

## 8. Switch to Codex

Only after dry-run mode is stable:

```bash
WORKER_BACKEND=codex-cli
```

Then restart:

```bash
cd /opt/hermes-codex-ops/system/docker
docker compose up -d --build
```

## Recovery

```bash
cat config/control-state.json
jq . tasks/pending.json
jq . tasks/awaiting_approval.json
less memory/summaries/context-pack.md
tail -n 100 logs/ops.jsonl
```

For Hostinger-specific browser/web-terminal recovery, see [HOSTINGER_RECOVERY.md](HOSTINGER_RECOVERY.md).
