from pathlib import Path

from system.services.memory import MemoryStore
from system.services.queue import TaskQueue


def test_queue_creates_and_exports_task(tmp_path: Path) -> None:
    queue = TaskQueue(database_path=tmp_path / "queue.sqlite3", tasks_dir=tmp_path / "tasks")
    task = queue.create(summary="test task", assigned_agent="codex", priority=7)

    assert task.status == "pending"
    assert (tmp_path / "tasks" / "pending.json").exists()
    assert queue.get(task.id).summary == "test task"


def test_queue_claims_next_task(tmp_path: Path) -> None:
    queue = TaskQueue(database_path=tmp_path / "queue.sqlite3", tasks_dir=tmp_path / "tasks")
    low = queue.create(summary="low", assigned_agent="codex", priority=1)
    high = queue.create(summary="high", assigned_agent="codex", priority=9)

    claimed = queue.claim_next()

    assert claimed.id == high.id
    assert queue.get(high.id).status == "active"
    assert queue.get(low.id).status == "pending"


def test_memory_appends_markdown(tmp_path: Path) -> None:
    memory = MemoryStore(root=tmp_path / "memory")
    memory.ensure_baseline()
    path = memory.append_markdown("active-projects.md", "Test", "Durable note.")

    assert path.exists()
    assert "Durable note." in path.read_text(encoding="utf-8")
