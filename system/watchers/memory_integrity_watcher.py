from __future__ import annotations

from system.services.audit_log import AuditLog
from system.services.memory import MemoryStore
from system.watchers.common import notify_telegram


REQUIRED = [
    "active-projects.md",
    "deployment-history.md",
    "github-state.md",
    "agent-status.md",
    "summaries/handoffs.md",
]


def main() -> None:
    audit = AuditLog()
    memory = MemoryStore()
    memory.ensure_baseline()
    missing = [item for item in REQUIRED if not (memory.root / item).exists()]
    result = "failed" if missing else "ok"
    if missing:
        notify_telegram(f"Memory integrity problem: missing {missing}")
    audit.write(agent="memory-integrity-watcher", action="scan", result=result, missing=missing)


if __name__ == "__main__":
    main()
