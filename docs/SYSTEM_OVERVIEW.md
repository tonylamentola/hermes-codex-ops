# System Overview

Hermes Codex Ops is a modular AI operations platform intended for long-running work on an Ubuntu VPS.

## Root Layout

- `/system/hermes`: orchestration, routing, context compression, dispatch
- `/system/telegram`: Telegram command center
- `/system/watchers`: scheduled monitoring workers
- `/system/services`: shared durable services
- `/system/services/worker.py`: durable task worker loop
- `/system/services/memory_compressor.py`: context pack generation
- `/system/services/control_state.py`: durable operator pause/resume state
- `/system/scripts`: operator scripts
- `/system/docker`: Docker runtime files
- `/memory`: persistent Markdown and JSON memory
- `/tasks`: queue exports and SQLite database
- `/logs`: append-only JSONL audit logs
- `/repos`: local repository checkouts
- `/config`: explicit configuration

## Bring-Up Scripts

- `system/scripts/bootstrap_ubuntu.sh`: install VPS prerequisites and initialize durable state
- `system/scripts/healthcheck.py`: inspect queue, control state, required files, and recent logs
- `system/scripts/live_smoke.sh`: run a local dry-run task through the worker path

## Durable State

Hermes can be deleted or replaced without losing state because permanent data is external:

- Memory: Markdown and JSON files
- Queue: SQLite plus JSON exports
- Logs: JSONL
- Repositories: Git checkouts in `/repos`
- Configuration: files under `/config` and environment variables

## Phase Roadmap

Phase 1 establishes the runtime, queue, logs, memory, Telegram commands, GitHub integration skeleton, and watcher entrypoints.

Phase 2 adds provider-specific deployment monitoring, automatic retries, richer notification delivery, and memory compression jobs. The first Phase 2 slice includes the worker loop and Telegram notifier.

Phase 3 adds local models, vector memory, advanced routing, and browser automation.
