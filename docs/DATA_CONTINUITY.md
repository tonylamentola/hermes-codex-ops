# Data Continuity

This system intentionally separates coordination from durable state. The operator should be able to recover from Hermes, Telegram, dashboard, or worker failure by inspecting files, SQLite, logs, GitHub, and the dashboard database.

## Sources Of Truth

- GitHub: code, reusable templates, workflow rules, docs.
- Vercel dashboard storage: live lead/task UI state, approvals, outreach statuses, trend reports.
- VPS SQLite queue: Hermes execution queue and worker state.
- VPS memory files: compressed handoffs, project state, GitHub/deployment state.
- VPS JSONL logs: append-only operational audit.
- VPS repo cache: local clones for worker context only. It is a cache, not the source of truth.

## Known Loss Points

- A dashboard task can be moved to `running` before the VPS accepts it. The dashboard route should put it back in `queued` if webhook delivery fails.
- A Hermes task can be created without enough project/template context. The coordinator now injects dashboard-sent template context or reads the VPS repo cache.
- A direct Telegram task can start in the wrong project if the message does not name one. Hermes should ask a clarifying question for ambiguous project/workspace tasks.
- Telegram task payloads now persist originating message text for future task submissions. Older tasks still lack raw message bodies, so `/export_chat` reconstructs those older conversations from queue rows and JSONL logs, including task summaries/results, but it cannot make historical raw text appear retroactively.
- Generated artifacts can be mentioned but not written. Worker checks required artifacts when the task payload declares them.
- Reply/outreach data can split across email, Facebook, Telegram, and dashboard if imports are manual. All replies should become dashboard lead events.
- GitHub watcher state can show commits but not local code. `system.scripts.sync_repo_cache` refreshes local repo caches from GitHub.
- Vercel deployments can be live while the VPS cache is stale. Run repo-cache sync after pushing template or workflow changes.

## Recovery Checks

```bash
cd /opt/hermes-codex-ops
. .venv/bin/activate
python -m system.scripts.healthcheck
python -m system.scripts.sync_repo_cache
sqlite3 tasks/queue.sqlite3 'select status,count(*) from tasks group by status;'
tail -n 100 logs/ops.jsonl
less memory/summaries/context-pack.md
python -m system.scripts.export_telegram_records --chat-id CHAT_ID --date YYYY-MM-DD
```

## Operator Rule

If a task changes code, templates, outreach statuses, leads, replies, or pricing decisions, it must be written to one durable source of truth before the worker marks it complete.
