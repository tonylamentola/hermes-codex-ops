# Deployment

The target environment is an Ubuntu VPS running Docker.

## Install

```bash
sudo apt update
sudo apt install -y git docker.io docker-compose-plugin sqlite3 jq
sudo usermod -aG docker "$USER"
```

Clone or copy this repository to `/opt/hermes-codex-ops`, then:

```bash
cd /opt/hermes-codex-ops
bash system/scripts/bootstrap_ubuntu.sh
cd system/docker
docker compose up -d --build
```

The Compose stack includes Hermes, Telegram, the durable worker, and initial watcher services. The Docker image installs the Codex CLI and mounts root's `/root/.codex` login directory read-only into Codex-calling services. Start with `WORKER_BACKEND=dry-run`; switch to `WORKER_BACKEND=codex-cli` after `codex login` works as root on the VPS and `docker compose run --rm worker codex login status` succeeds, or `WORKER_BACKEND=codex-api` only after `OPENAI_API_KEY` is configured.

For first live use, consider setting:

```bash
WORKER_REQUIRE_APPROVAL=true
```

Then approve tasks through Telegram with `/approve TASK_ID` or from the VPS shell:

```bash
python -m system.scripts.control approve TASK_ID
```

## Manual Health Checks

```bash
docker compose ps
tail -n 30 ../../logs/ops.jsonl
sqlite3 ../../tasks/queue.sqlite3 'select status,count(*) from tasks group by status;'
```

## Deployment Watcher

Deployment checks are configured through `config/repos.json`. Each repository may define `healthcheck_url`; if omitted, `deployment_url` is used. The watcher performs HTTP GET checks and writes:

- `memory/deployment-history.md`
- `memory/deployment-state.json`
- `logs/ops.jsonl`

Run manually:

```bash
python -m system.watchers.deployment_watcher
```
