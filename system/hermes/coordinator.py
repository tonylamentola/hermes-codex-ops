from __future__ import annotations

from dataclasses import dataclass

from system.services.ai_backend import AIBackend, DryRunBackend
from system.services.audit_log import AuditLog
from system.services.memory import MemoryStore
from system.services.queue import Task, TaskQueue


HERMES_SYSTEM_PROMPT = """Hermes coordinates AI operations.
Use durable memory, task, and log systems as the source of truth.
Inject only relevant context. Return concise, auditable worker instructions."""


@dataclass
class HermesCoordinator:
    queue: TaskQueue
    memory: MemoryStore
    audit: AuditLog
    backend: AIBackend

    @classmethod
    def create(cls, backend: AIBackend | None = None) -> "HermesCoordinator":
        return cls(TaskQueue(), MemoryStore(), AuditLog(), backend or DryRunBackend())

    async def submit_task(self, summary: str, *, priority: int = 5, payload: dict | None = None) -> Task:
        self.memory.ensure_baseline()
        task = self.queue.create(summary=summary, assigned_agent="codex", priority=priority, payload=payload)
        self.memory.append_markdown(
            "active-projects.md",
            "Task submitted",
            f"- Task: `{task.id}`\n- Summary: {summary}\n- Assigned agent: codex",
        )
        self.audit.write(agent="hermes", action="submit_task", result="queued", task_id=task.id)
        return task

    async def prepare_worker_context(self, task_id: str) -> str:
        task = self.queue.get(task_id)
        if not task:
            raise KeyError(task_id)
        relevant_memory = "\n\n".join(
            [
                self.memory.read_markdown("summaries/context-pack.md", max_chars=6000),
                self.memory.read_markdown("active-projects.md"),
                self.memory.read_markdown("github-state.md"),
                self.memory.read_markdown("agent-status.md"),
            ]
        )
        prompt = f"Task:\n{task.summary}\n\nPayload:\n{task.payload}\n\nRelevant memory:\n{relevant_memory}"
        context = await self.backend.complete(prompt, system=HERMES_SYSTEM_PROMPT)
        self.audit.write(agent="hermes", action="prepare_worker_context", result="ok", task_id=task.id)
        return context

    def status(self) -> dict:
        counts = {
            status: len(self.queue.list(status=status, limit=500))
            for status in (
                "pending",
                "active",
                "awaiting_approval",
                "stalled",
                "completed",
                "failed",
                "cancelled",
            )
        }
        return {"queue": counts, "recent_logs": self.audit.tail(5)}
