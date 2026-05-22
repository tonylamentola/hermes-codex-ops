from __future__ import annotations

from datetime import datetime, timedelta, timezone

from system.services.audit_log import AuditLog
from system.services.queue import TaskQueue
from system.watchers.common import notify_telegram


def main(max_age_minutes: int = 60) -> None:
    audit = AuditLog()
    queue = TaskQueue()
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
    marked = 0
    for task in queue.list(status="active", limit=500):
        updated = datetime.fromisoformat(task.updated_at)
        if updated < cutoff:
            queue.update_status(task.id, "stalled")
            marked += 1
            notify_telegram(f"Task stalled: {task.id} {task.summary}")
    audit.write(agent="stalled-task-watcher", action="scan", result="ok", marked=marked)


if __name__ == "__main__":
    main()
