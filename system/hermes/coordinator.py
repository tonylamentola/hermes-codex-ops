from __future__ import annotations

from dataclasses import dataclass

from system.services.ai_backend import AIBackend, DryRunBackend
from system.services.audit_log import AuditLog
from system.services.memory import MemoryStore
from system.services.queue import Task, TaskQueue


HERMES_SYSTEM_PROMPT = """Hermes coordinates AI operations.
Use durable memory, task, and log systems as the source of truth.
Inject only relevant context. Return concise, auditable worker instructions.

For outreach, niche research, flyer concepts, website concepts, lead previews, and visual-template work:
- Use repo-owned DESIGN.md, SKILL.md, and niche.json context when it is present.
- Treat Hermes as coordinator/router/supervisor, not as the owner of permanent template state.
- Preserve the review flow: gather/research, generate concepts, prepare previews, wait for approval, then execute/send/track.
- Do not create one-off hidden templates. Save reusable template decisions in human-readable files or dashboard state.
- If a needed niche template is missing, create a follow-up task to add it instead of improvising silently."""


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
        design_context = task.payload.get("design_template_context")
        if isinstance(design_context, dict):
            design_body = str(design_context.get("body") or "").strip()
            detected = design_context.get("detectedNiches") or design_context.get("detected_niches") or []
            if design_body:
                relevant_memory = "\n\n".join(
                    [
                        relevant_memory,
                        "REPO_OWNED_DESIGN_TEMPLATE_CONTEXT\n"
                        f"Detected niches: {detected}\n"
                        "Use this context for outreach/niche/flyer/website/template tasks. "
                        "Do not treat it as permanent Hermes memory; it belongs to the project repo/dashboard.\n\n"
                        f"{design_body}",
                    ]
                )
        context = (
            "WORKER_CONTEXT\n\n"
            f"Task ID: {task.id}\n"
            f"Task summary: {task.summary}\n\n"
            f"Payload:\n{task.payload}\n\n"
            f"Relevant durable memory:\n{relevant_memory}"
        )
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
