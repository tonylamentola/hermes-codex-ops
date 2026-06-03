import asyncio
from pathlib import Path

from system.hermes.capabilities import CapabilityPlanner
from system.hermes.coordinator import HermesCoordinator
from system.services.ai_backend import DryRunBackend
from system.services.audit_log import AuditLog
from system.services.memory import MemoryStore
from system.services.queue import TaskQueue


def test_capability_audit_names_external_hermes_agent_runtime() -> None:
    findings = CapabilityPlanner().audit()

    assert any(item["name"] == "Provider proxy / public Hermes Agent runtime" for item in findings)
    assert any(item["status"] == "enabled-by-this-repo" for item in findings)


def test_planner_creates_agent_lanes_for_broad_work() -> None:
    planned = CapabilityPlanner().plan(
        "Research Hermes offerings, audit setup, implement changes, and create skills",
        priority=5,
    )

    agents = {item.assigned_agent for item in planned}
    assert {"codex-research", "codex-implementation", "codex-verification", "codex-improvement"} <= agents


def test_submit_task_can_decompose_into_subtasks(tmp_path: Path) -> None:
    queue = TaskQueue(database_path=tmp_path / "tasks" / "queue.sqlite3", tasks_dir=tmp_path / "tasks")
    memory = MemoryStore(root=tmp_path / "memory")
    audit = AuditLog(path=tmp_path / "logs" / "ops.jsonl")
    hermes = HermesCoordinator(queue=queue, memory=memory, audit=audit, backend=DryRunBackend())

    root = asyncio.run(
        hermes.submit_task(
            "Research Hermes offerings, audit setup, implement changes, and create skills",
            decompose=True,
        )
    )
    subtasks = [task for task in queue.list(status="pending", limit=10) if task.payload.get("coordination", {}).get("root_task_id") == root.id]

    assert queue.get(root.id).status == "planned"
    assert len(subtasks) >= 4
    assert {task.assigned_agent for task in subtasks} >= {
        "codex-research",
        "codex-implementation",
        "codex-verification",
        "codex-improvement",
    }
