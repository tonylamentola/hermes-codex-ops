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

Workers claim one assigned-agent lane at a time. The default lane is `codex`.

```bash
python -m system.services.worker --agent codex-research
python -m system.services.worker --agent codex-implementation
python -m system.services.worker --agent codex-verification
python -m system.services.worker --agent codex-improvement
```

Use lane-specific workers when Hermes decomposes broad work into research,
implementation, verification, documentation, and improvement subtasks.

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

## Recovery

```bash
sqlite3 tasks/queue.sqlite3 'select id,status,retry_count,summary from tasks order by updated_at desc;'
jq . tasks/active.json
jq . tasks/failed.json
tail -n 50 logs/ops.jsonl
```
