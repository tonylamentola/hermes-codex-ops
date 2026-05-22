# Watchers

Watchers are lightweight scheduled services. They do not own state; they inspect durable stores and write logs.

## Initial Watchers

- `deployment_watcher`: config-driven HTTP health checks for deployment URLs
- `stalled_task_watcher`: marks old active tasks as stalled
- `memory_integrity_watcher`: verifies required memory files exist
- `memory_compression_watcher`: refreshes compact context packs
- `queue_watcher`: exports SQLite queue to JSON
- `github_sync_watcher`: config-driven repository, branch, and commit summaries

## Running Manually

```bash
python -m system.watchers.queue_watcher
python -m system.watchers.stalled_task_watcher
python -m system.watchers.memory_integrity_watcher
python -m system.watchers.github_sync_watcher
python -m system.watchers.deployment_watcher
```

## Docker Schedule

Docker Compose runs these watcher loops:

- Queue export every 5 minutes
- Stalled task scan every 5 minutes
- Deployment scan every 5 minutes
- Memory integrity scan every 10 minutes
- Memory compression every 30 minutes
- GitHub sync every 15 minutes

## Notifications

Watchers call the shared Telegram notifier. Missing Telegram configuration does not crash the watcher; it creates an audit record with `result="skipped"` and the reason.
