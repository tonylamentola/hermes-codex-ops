from __future__ import annotations

from system.services.audit_log import AuditLog
from system.services.queue import TaskQueue


def main() -> None:
    queue = TaskQueue()
    queue.export_json()
    counts = {
        status: len(queue.list(status=status, limit=1000))
        for status in ("pending", "planned", "active", "awaiting_approval", "stalled", "completed", "failed", "cancelled")
    }
    AuditLog().write(agent="queue-watcher", action="export_json", result="ok", counts=counts)


if __name__ == "__main__":
    main()
