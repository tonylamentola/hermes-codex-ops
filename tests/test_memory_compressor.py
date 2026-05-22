from pathlib import Path

from system.services.memory import MemoryStore
from system.services.memory_compressor import deterministic_summary, extract_recent_entries


def test_deterministic_summary_includes_recent_memory(tmp_path: Path) -> None:
    memory = MemoryStore(root=tmp_path / "memory")
    memory.ensure_baseline()
    memory.append_markdown("active-projects.md", "Project A", "Keep this context.")

    summary = deterministic_summary(memory)

    assert "# Context Pack" in summary
    assert "Project A" in summary
    assert "Keep this context." in summary


def test_extract_recent_entries_splits_timestamped_sections() -> None:
    text = "# Title\n\n## 2026-05-22T01:00:00+00:00 - One\n\nA\n\n## 2026-05-22T02:00:00+00:00 - Two\n\nB\n"

    entries = extract_recent_entries(text)

    assert len(entries) == 2
    assert entries[0].startswith("## 2026-05-22T01")
    assert entries[1].startswith("## 2026-05-22T02")
