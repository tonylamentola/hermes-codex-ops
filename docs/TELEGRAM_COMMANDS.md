# Telegram Commands

Telegram is the command center and notification surface.

## Commands

- Plain text message: create a pending Hermes task from the message
- `/status`: queue counts and platform status
- `/submit TASK SUMMARY`: create a pending task from Telegram
- `/projects`: active project memory
- `/deployments`: deployment history
- `/tasks`: recent tasks
- `/stalled`: stalled tasks
- `/logs`: recent audit log entries
- `/retry TASK_ID`: requeue a task and increment retry count
- `/pause optional reason`: pause worker task claiming
- `/resume`: resume worker task claiming
- `/cancel TASK_ID`: mark a task cancelled
- `/approve TASK_ID`: approve a task when approval mode is enabled
- `/memory`: recent active memory
- `/agents`: agent status memory

## Security

Set `TELEGRAM_ALLOWED_CHAT_IDS` in `.env` to restrict command access. Use a comma-separated list of numeric chat IDs.

## Notifications

Watcher and worker notifications are sent with Telegram's HTTP API when `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ALLOWED_CHAT_IDS` are configured. If either value is missing, the notification attempt is logged as skipped in JSONL instead of failing the watcher.

Tasks created from plain Telegram text include the originating chat ID in the task payload. Worker updates for those tasks are sent back to that chat when the task starts, completes, fails, retries, or needs approval.
