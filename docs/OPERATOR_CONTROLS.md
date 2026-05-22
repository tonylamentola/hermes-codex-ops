# Operator Controls

Operator controls are durable and inspectable. Telegram and CLI commands write the same state files.

## Pause and Resume

Pause state lives in `config/control-state.json`.

```bash
python -m system.scripts.control pause "maintenance window"
python -m system.scripts.control status
python -m system.scripts.control resume
```

Telegram:

- `/pause optional reason`
- `/resume`

When paused, the worker logs `result="paused"` and does not claim pending tasks.

## Cancel

```bash
python -m system.scripts.control cancel TASK_ID
```

Telegram:

- `/cancel TASK_ID`

Cancelled tasks are exported to `tasks/cancelled.json`.

Cancellation is a queue-level control. It prevents future processing for tasks that have not already been claimed; it does not forcibly kill an already-running backend request.

## Approval Gate

Set this in `.env`:

```bash
WORKER_REQUIRE_APPROVAL=true
```

When enabled, the worker moves unapproved pending tasks to `awaiting_approval` and notifies Telegram. Approve with:

```bash
python -m system.scripts.control approve TASK_ID
```

Telegram:

- `/approve TASK_ID`

Approved tasks are moved back to pending with `payload.approved=true`.

## Recovery

```bash
cat config/control-state.json
jq . tasks/awaiting_approval.json
jq . tasks/cancelled.json
tail -n 50 logs/ops.jsonl
```
