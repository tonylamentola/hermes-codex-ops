# Worker

The worker is the bridge between durable queue state and the reasoning backend.

## Responsibilities

- Claim the next pending task atomically.
- Mark it active.
- Ask Hermes to prepare compressed worker context.
- Call the configured backend through Hermes.
- Store the result in task payload.
- Append a handoff summary.
- Mark the task completed, failed, or pending for retry.
- Notify Telegram when configured.

## Running

```bash
python -m system.services.worker --once
python -m system.services.worker
```

## Backend Selection

Use dry-run mode for smoke tests:

```bash
WORKER_BACKEND=dry-run python -m system.services.worker --once
```

Use Codex API:

```bash
WORKER_BACKEND=codex-api OPENAI_API_KEY=... python -m system.services.worker
```

Use Codex CLI subscription login:

```bash
codex login
WORKER_BACKEND=codex-cli CODEX_CLI_SANDBOX=read-only python -m system.services.worker
```

`CODEX_CLI_TIMEOUT_SECONDS` defaults to `600`. When the CLI exceeds that limit,
Hermes terminates the Codex process group and records a normal worker failure
instead of hanging while waiting for logs/results.

## Recovery

```bash
sqlite3 tasks/queue.sqlite3 'select id,status,retry_count,summary from tasks order by updated_at desc;'
jq . tasks/active.json
jq . tasks/failed.json
tail -n 50 logs/ops.jsonl
```
