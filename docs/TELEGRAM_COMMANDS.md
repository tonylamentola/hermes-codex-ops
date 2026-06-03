# Telegram Commands

Telegram is the command center and notification surface.

## Commands

- Plain text message: create a pending Hermes task from the message and show Approve/Cancel/Details buttons
- `approve`, `yes`, `run it`, `go ahead`, or `do it`: approve the latest pending task from that chat
- `cancel`, `stop`, `no`, or `nevermind`: cancel the latest pending task from that chat
- `/status`: queue counts and platform status
- `/submit TASK SUMMARY`: create a pending task from Telegram
- `/plan TASK SUMMARY`: create a root task and decomposition subtasks across named worker lanes
- `/audit_capabilities`: write and display the current Hermes capability audit
- `/projects`: active project memory
- `/deployments`: deployment history
- `/tasks`: recent tasks
- `/task TASK_ID`: show status, result preview, backend, and reported artifacts
- `/artifacts TASK_ID`: send reported artifact files/images when they exist on the VPS
- `/stalled`: stalled tasks
- `/logs`: recent audit log entries
- `/export_chat optional-YYYY-MM-DD`: create and send a durable Hermes chat export for the current Telegram chat
- `/retry TASK_ID`: requeue a task and increment retry count
- `/pause optional reason`: pause worker task claiming
- `/resume`: resume worker task claiming
- `/cancel TASK_ID`: mark a specific task cancelled
- `/approve TASK_ID`: approve a specific task when approval mode is enabled
- `/memory`: recent active memory
- `/agents`: agent status memory

## Security

Set `TELEGRAM_ALLOWED_CHAT_IDS` in `.env` to restrict command access. Use a comma-separated list of numeric chat IDs.

## Notifications

Watcher and worker notifications are sent with Telegram's HTTP API when `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ALLOWED_CHAT_IDS` are configured. If either value is missing, the notification attempt is logged as skipped in JSONL instead of failing the watcher.

Tasks created from plain Telegram text include the originating chat ID in the task payload. Worker updates for those tasks are sent back to that chat when the task starts, completes, fails, retries, or needs approval. Full task IDs remain available for recovery, but the normal mobile flow should use buttons or short text replies.

Completed tasks store a `worker_context` result preview and an `artifacts` list in the task payload. The worker extracts artifact paths from backend output, marks whether each file exists, and sends up to three existing image artifacts back to Telegram automatically. Use `/artifacts TASK_ID` to resend available files.

## Durable Chat Exports

Use `/export_chat` to create a text export from durable Hermes records for the current chat. The export includes chat-linked task summaries, persisted message text when available, approvals, worker events, notifier events, and available result previews.

Raw Telegram message text is persisted for future task submissions in the task payload. Older tasks created before message-text persistence remain an auditable operations timeline, not a verbatim Telegram chat transcript.

The same export can be generated on the VPS:

```bash
python -m system.scripts.export_telegram_records --chat-id CHAT_ID --date YYYY-MM-DD
```
