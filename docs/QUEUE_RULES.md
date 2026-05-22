# Queue Rules

The task queue must survive process crashes and VPS restarts.

## Storage

- SQLite source of truth: `tasks/queue.sqlite3`
- Human-readable exports:
  - `tasks/pending.json`
  - `tasks/active.json`
  - `tasks/stalled.json`
  - `tasks/completed.json`

## Task Fields

Every task has:

- `id`
- `timestamp`
- `assigned_agent`
- `priority`
- `retry_count`
- `status`
- `summary`
- `payload`
- `updated_at`

## Statuses

- `pending`: ready for assignment
- `active`: assigned and being worked
- `stalled`: exceeded watcher threshold
- `completed`: finished
- `failed`: failed but not yet retried or resolved
- `cancelled`: stopped by an operator
- `awaiting_approval`: waiting for explicit operator approval

## Worker Loop

The worker claims one pending task at a time with an atomic SQLite update:

```bash
python -m system.services.worker --once
python -m system.services.worker
```

Set `WORKER_BACKEND=dry-run` for smoke tests. Set `WORKER_BACKEND=codex-cli` to use the Codex CLI login, or `WORKER_BACKEND=codex-api` with `OPENAI_API_KEY` for direct API use.

Failures are retried until `WORKER_MAX_RETRIES` is reached. Retry attempts are logged, exported to JSON, and announced through Telegram when configured.

Set `WORKER_REQUIRE_APPROVAL=true` to require `/approve TASK_ID` before the worker processes pending tasks.

## Recovery

```bash
sqlite3 tasks/queue.sqlite3 'select id,status,summary,updated_at from tasks order by updated_at desc;'
jq . tasks/pending.json
jq . tasks/failed.json
python -m system.watchers.queue_watcher
```
