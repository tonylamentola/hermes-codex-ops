import json
from pathlib import Path

from system.hermes.openai_adapter import (
    MODEL_ID,
    _completion_payload,
    _stream_events,
    _system_with_memory,
    _webui_memory_context,
)
from system.services.memory import MemoryStore


def test_completion_payload_matches_openai_shape() -> None:
    payload = _completion_payload("hello", 123)

    assert payload["object"] == "chat.completion"
    assert payload["model"] == MODEL_ID
    assert payload["choices"][0]["message"] == {"role": "assistant", "content": "hello"}
    assert payload["choices"][0]["finish_reason"] == "stop"


def test_stream_events_match_openai_sse_shape() -> None:
    events = list(_stream_events("hello", 123))

    assert events[-1] == "data: [DONE]\n\n"
    role_chunk = json.loads(events[0].removeprefix("data: "))
    content_chunk = json.loads(events[1].removeprefix("data: "))
    final_chunk = json.loads(events[2].removeprefix("data: "))

    assert role_chunk["object"] == "chat.completion.chunk"
    assert role_chunk["choices"][0]["delta"] == {"role": "assistant"}
    assert content_chunk["choices"][0]["delta"] == {"content": "hello"}
    assert final_chunk["choices"][0]["finish_reason"] == "stop"


def test_webui_memory_context_includes_github_state(tmp_path: Path) -> None:
    memory = MemoryStore(root=tmp_path / "memory")
    memory.ensure_baseline()
    memory.append_markdown("github-state.md", "GitHub sync", "- `owner/repo` `main` abc123 Latest commit")
    memory.append_markdown("active-projects.md", "Codex job tracker sync", "- Open jobs: `3`")

    context = _webui_memory_context(memory)

    assert "Hermes durable memory snapshot follows" in context
    assert "owner/repo" in context
    assert "Open jobs" in context


def test_system_with_memory_appends_context() -> None:
    system = _system_with_memory("Base system", "Memory snapshot")

    assert system == "Base system\n\nMemory snapshot"
