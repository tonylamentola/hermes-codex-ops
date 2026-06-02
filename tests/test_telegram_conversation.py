from pathlib import Path

from system.services.audit_log import AuditLog
from system.services.memory import MemoryStore
from system.services.queue import TaskQueue
from system.telegram.conversation import _build_system_prompt, _build_user_prompt


def test_conversation_system_prompt_gives_codex_like_operating_contract() -> None:
    prompt = _build_system_prompt()

    assert "Think like a senior Codex operator" in prompt
    assert "files, repos, shell commands, browsers, VPS access" in prompt
    assert "[[QUEUE:" in prompt
    assert "Never pretend to have clicked" in prompt


def test_conversation_prompt_includes_project_map_and_routing_context(tmp_path: Path) -> None:
    memory = MemoryStore(root=tmp_path / "memory")
    memory.ensure_baseline()
    queue = TaskQueue(database_path=tmp_path / "tasks" / "queue.sqlite3", tasks_dir=tmp_path / "tasks")
    audit = AuditLog(path=tmp_path / "logs" / "ops.jsonl")

    prompt = _build_user_prompt(
        "Why is Hermes bad conversationally?",
        chat_id=7272977804,
        queue=queue,
        memory=memory,
        audit=audit,
    )

    assert "--- How to respond ---" in prompt
    assert "--- Known project map ---" in prompt
    assert "Hermes Ops" in prompt
    assert "HERMES_CONTEXT_PACKET" in prompt
    assert "queue the work" in prompt
