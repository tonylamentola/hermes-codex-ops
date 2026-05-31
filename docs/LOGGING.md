# Logging

All important actions must write append-only JSONL records to `/logs`.

## Required Fields

- `timestamp`
- `agent`
- `action`
- `result`
- `error` when applicable

## Example

```json
{"timestamp":"2026-05-22T21:44:00+00:00","agent":"deployment-watcher","action":"vercel_deploy_check","result":"failed","reason":"missing env variable"}
```

## Recovery

```bash
tail -n 50 logs/ops.jsonl
jq -c 'select(.result=="failed")' logs/ops.jsonl
```

Hermes reads recent log entries with a bounded tail reader so large audit logs
do not block status, healthcheck, or Telegram `/logs` responses.
