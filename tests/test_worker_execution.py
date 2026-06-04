from pathlib import Path
import asyncio

from system.hermes.coordinator import HermesCoordinator
from system.services.audit_log import AuditLog
from system.services.control_state import ControlState
from system.services.memory import MemoryStore
from system.services.queue import TaskQueue
from system.services.worker import Worker, auto_send_artifacts


class FakeBackend:
    name = "fake"

    def __init__(self, result: str) -> None:
        self.result = result

    async def complete(self, prompt: str, *, system: str = "") -> str:
        assert "WORKER_CONTEXT" in prompt
        return self.result


class FakeNotifier:
    def __init__(self) -> None:
        self.messages: list[str] = []
        self.files: list[str] = []

    async def send(self, message: str, *, chat_ids=None) -> int:
        self.messages.append(message)
        return 1

    async def send_file(self, path: str, *, caption: str = "", chat_ids=None) -> int:
        self.files.append(path)
        return 1


def test_worker_executes_backend_and_extracts_artifacts_from_result(tmp_path: Path) -> None:
    artifact = tmp_path / "artifacts" / "final.png"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"png")
    queue = TaskQueue(database_path=tmp_path / "tasks" / "queue.sqlite3", tasks_dir=tmp_path / "tasks")
    memory = MemoryStore(root=tmp_path / "memory")
    audit = AuditLog(path=tmp_path / "logs" / "ops.jsonl")
    hermes = HermesCoordinator(
        queue=queue,
        memory=memory,
        audit=audit,
        backend=FakeBackend(f"Done. Final image: {artifact}"),
    )
    notifier = FakeNotifier()
    control = ControlState(path=tmp_path / "config" / "control-state.json", audit=audit)
    queue.create(summary="Create final image", assigned_agent="codex", payload={"approved": True})

    worker = Worker(queue=queue, memory=memory, audit=audit, notifier=notifier, hermes=hermes, control=control)
    completed = asyncio.run(worker.run_once())

    assert completed is not None
    fresh = queue.get(completed.id)
    assert fresh is not None
    assert fresh.status == "completed"
    assert "WORKER_CONTEXT" in fresh.payload["worker_context"]
    assert fresh.payload["worker_result"] == f"Done. Final image: {artifact}"
    assert fresh.payload["artifacts"][0]["display_path"] == str(artifact)
    assert notifier.files == [str(artifact)]
    assert "Done. Final image:" in notifier.messages[-1]
    assert "context-pack.md" not in notifier.messages[-1]


def test_worker_completion_includes_result_when_artifacts_are_not_sendable(tmp_path: Path) -> None:
    memory_file = tmp_path / "memory" / "agent-status.md"
    memory_file.parent.mkdir(parents=True)
    memory_file.write_text("status", encoding="utf-8")
    result = f"Runtime smoketest complete. Codex exec works. Recorded result in `{memory_file}`."
    queue = TaskQueue(database_path=tmp_path / "tasks" / "queue.sqlite3", tasks_dir=tmp_path / "tasks")
    memory = MemoryStore(root=tmp_path / "memory")
    audit = AuditLog(path=tmp_path / "logs" / "ops.jsonl")
    hermes = HermesCoordinator(queue=queue, memory=memory, audit=audit, backend=FakeBackend(result))
    notifier = FakeNotifier()
    control = ControlState(path=tmp_path / "config" / "control-state.json", audit=audit)
    queue.create(summary="Runtime smoke", assigned_agent="codex", payload={"approved": True})

    worker = Worker(queue=queue, memory=memory, audit=audit, notifier=notifier, hermes=hermes, control=control)
    completed = asyncio.run(worker.run_once())

    assert completed is not None
    assert notifier.files == []
    assert "Runtime smoketest complete. Codex exec works." in notifier.messages[-1]
    assert "I found artifact paths, but no Telegram-sendable files." in notifier.messages[-1]


def test_auto_send_artifacts_excludes_context_docs() -> None:
    artifacts = [
        {"path": "/tmp/context-pack.md", "exists": True, "kind": "file"},
        {"path": "/tmp/niche.json", "exists": True, "kind": "file"},
        {"path": "/tmp/flyer.svg", "exists": True, "kind": "file"},
        {"path": "/tmp/final.png", "exists": True, "kind": "image"},
    ]

    selected = auto_send_artifacts(artifacts)

    assert [Path(item["path"]).name for item in selected] == ["final.png", "flyer.svg"]
