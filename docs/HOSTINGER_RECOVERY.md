# Hostinger VPS Recovery

This document records the verified recovery path for the live Hermes VPS.

## Verified Live Location

- Hostinger VPS label: `srv1508270`
- Hermes root: `/opt/hermes-codex-ops`
- Durable logs: `/opt/hermes-codex-ops/logs/ops.jsonl`
- Queue database: `/opt/hermes-codex-ops/tasks/queue.sqlite3`
- Queue JSON exports: `/opt/hermes-codex-ops/tasks/*.json`
- Memory files: `/opt/hermes-codex-ops/memory`
- Chat exports: `/opt/hermes-codex-ops/artifacts/chat-exports`

## Browser Recovery Route

If normal local browser automation cannot attach to Chrome, use a fresh Edge window with a local DevTools port, then sign in to Hostinger in that window:

```powershell
$profile = Join-Path $env:TEMP 'codex-edge-hostinger-profile'
New-Item -ItemType Directory -Force -Path $profile | Out-Null
Start-Process 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe' -ArgumentList @(
  '--remote-debugging-port=9223',
  "--user-data-dir=$profile",
  '--no-first-run',
  '--new-window',
  'https://hpanel.hostinger.com/vps/1508270/docker-manager'
)
```

After login, Hostinger Docker Manager can open a web terminal. If the terminal opens inside a Docker container, run:

```bash
exit
```

That returns to the host shell:

```bash
root@srv1508270:~#
```

From the host shell:

```bash
cd /opt/hermes-codex-ops
. .venv/bin/activate 2>/dev/null || true
python -m system.scripts.healthcheck
tail -n 80 logs/ops.jsonl
sqlite3 tasks/queue.sqlite3 'select status,count(*) from tasks group by status;'
```

## Telegram Export Recovery

Telegram message text is stored for future task submissions in durable task payloads. Older records may only have the durable audit trail, chat-linked task summaries, approvals, worker lifecycle, and available result previews.

From Telegram:

```text
/export_chat
/export_chat 2026-06-01
```

From the VPS:

```bash
cd /opt/hermes-codex-ops
. .venv/bin/activate 2>/dev/null || true
python -m system.scripts.export_telegram_records --chat-id 7272977804 --date 2026-06-01
```

The default output path is:

```text
artifacts/chat-exports/<date>-chat-<chat-id>.txt
```

## Operator Rule

Prefer `/export_chat` or `system.scripts.export_telegram_records` before manually scraping logs. Manual Hostinger terminal extraction is a fallback only.
