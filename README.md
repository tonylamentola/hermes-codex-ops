# Hermes Codex Ops

Persistent AI operations platform for an Ubuntu VPS. Hermes coordinates and supervises work, while durable state lives in simple external systems:

- `/memory` for Markdown summaries and JSON state
- `/tasks` for exported task queue snapshots plus SQLite
- `/logs` for append-only JSONL audit records
- `/repos` for checked-out repositories
- `/config` for explicit operator-managed configuration

Hermes is replaceable. If it fails, a human can inspect memory, queue state, and logs with `less`, `jq`, `sqlite3`, and Git.

## Quick Start

```bash
cd /opt/hermes-codex-ops
cp .env.example .env
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
python -m system.scripts.init_platform
python -m system.hermes.main submit "Test durable queue"
python -m system.services.worker --once
python -m system.hermes.main status
```

Docker:

```bash
cd /opt/hermes-codex-ops/system/docker
docker compose up --build
```

VPS bring-up:

```bash
bash system/scripts/bootstrap_ubuntu.sh
python -m system.scripts.healthcheck
```

## Operating Model

1. Telegram receives commands and notifications.
2. Hermes classifies tasks, selects the backend, compresses context, and dispatches.
3. Codex performs coding and reasoning work from compressed, relevant context.
4. Queue state is stored in SQLite and exported to JSON.
5. Memory is appended as Markdown and summarized over time.
6. Watchers scan for stalled tasks, memory issues, queue drift, GitHub state, and deployment state.
7. Every important action writes a JSONL audit record.

## Phase 1 Included

- Python backend scaffold
- Docker Compose services
- Telegram command center
- SQLite task queue with JSON exports
- Markdown memory store
- JSONL audit log
- GitHub API service skeleton
- Config-driven GitHub and deployment watchers
- Durable worker loop
- Real Telegram notifier service
- Memory compression and context packs
- Operator pause/resume/cancel/approval controls
- VPS bootstrap and health-check scripts
- Recovery-focused documentation

## Important Rule

Do not add hidden state. New durable systems must be documented, inspectable, and recoverable without Hermes.
