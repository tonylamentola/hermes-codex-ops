from __future__ import annotations

from system.services.audit_log import AuditLog
from system.services.memory import MemoryStore
from system.services.queue import TaskQueue


def main() -> None:
    memory = MemoryStore()
    memory.ensure_baseline()
    queue = TaskQueue()
    queue.export_json()
    audit = AuditLog()
    audit.write(agent="init-platform", action="initialize", result="ok")
    print("Initialized memory, task queue, and audit log.")


if __name__ == "__main__":
    main()
