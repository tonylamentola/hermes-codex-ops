from __future__ import annotations

import re
from dataclasses import dataclass

from system.services.ai_backend import CodexBackend, CodexCliBackend, DryRunBackend
from system.services.audit_log import AuditLog, utc_now
from system.services.memory import MemoryStore
from system.services.settings import settings


MEMORY_FILES = [
    "active-projects.md",
    "agent-status.md",
    "github-state.md",
    "deployment-history.md",
    "summaries/handoffs.md",
]


def choose_backend():
    if settings.memory_compression_backend in {"codex-api", "codex"}:
        return CodexBackend()
    if settings.memory_compression_backend == "codex-cli":
        return CodexCliBackend()
    return DryRunBackend()


def extract_recent_entries(markdown: str, limit: int = 12) -> list[str]:
    entries = re.split(r"\n(?=## \d{4}-\d{2}-\d{2}T)", markdown)
    entries = [entry.strip() for entry in entries if entry.strip().startswith("## ")]
    return entries[-limit:]


def deterministic_summary(memory: MemoryStore) -> str:
    sections = [f"# Context Pack\n\nGenerated: {utc_now()}\n"]
    for relative in MEMORY_FILES:
        text = memory.read_full_markdown(relative)
        entries = extract_recent_entries(text)
        sections.append(f"\n## {relative}\n")
        if entries:
            sections.extend(f"\n{entry}\n" for entry in entries)
        else:
            sections.append("No timestamped entries yet.")
    return "\n".join(sections).strip() + "\n"


@dataclass
class MemoryCompressor:
    memory: MemoryStore
    audit: AuditLog

    @classmethod
    def create(cls) -> "MemoryCompressor":
        return cls(memory=MemoryStore(), audit=AuditLog())

    async def build_context_pack(self) -> str:
        self.memory.ensure_baseline()
        deterministic = deterministic_summary(self.memory)
        if settings.memory_compression_backend != "codex":
            self.audit.write(
                agent="memory-compressor",
                action="build_context_pack",
                result="ok",
                backend="deterministic",
            )
            return deterministic[-settings.memory_context_max_chars :]

        backend = choose_backend()
        prompt = f"""Compress this AI operations memory into a concise handoff context.
Preserve current projects, active risks, failed systems, repo/deployment state, and next actions.
Do not invent facts. Keep it human-readable Markdown.

{deterministic[-settings.memory_context_max_chars:]}"""
        summary = await backend.complete(prompt, system="You compress operational memory for durable AI handoffs.")
        self.audit.write(
            agent="memory-compressor",
            action="build_context_pack",
            result="ok",
            backend=backend.name,
        )
        return summary.strip() + "\n"

    async def write_context_pack(self) -> str:
        context = await self.build_context_pack()
        self.memory.write_json_state(
            "summaries/context-pack.json",
            {
                "generated_at": utc_now(),
                "backend": settings.memory_compression_backend,
                "max_chars": settings.memory_context_max_chars,
                "content": context,
            },
        )
        path = self.memory.root / "summaries" / "context-pack.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(context, encoding="utf-8")
        self.memory.append_markdown(
            "summaries/handoffs.md",
            "Context pack refreshed",
            f"- Backend: `{settings.memory_compression_backend}`\n- Output: `memory/summaries/context-pack.md`",
        )
        self.audit.write(agent="memory-compressor", action="write_context_pack", result="ok", path=str(path))
        return context


async def main_async() -> None:
    await MemoryCompressor.create().write_context_pack()


def main() -> None:
    import asyncio

    asyncio.run(main_async())


if __name__ == "__main__":
    main()
