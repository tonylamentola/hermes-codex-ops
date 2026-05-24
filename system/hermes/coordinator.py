from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from system.services.ai_backend import AIBackend, DryRunBackend
from system.services.audit_log import AuditLog
from system.services.context_router import ContextRouter, context_packet_to_markdown
from system.services.memory import MemoryStore
from system.services.queue import Task, TaskQueue
from system.services.settings import settings


HERMES_SYSTEM_PROMPT = """Hermes coordinates AI operations.
Use durable memory, task, and log systems as the source of truth.
Inject only relevant context. Return concise, auditable worker instructions.

For outreach, niche research, flyer concepts, website concepts, lead previews, and visual-template work:
- Use repo-owned DESIGN.md, SKILL.md, and niche.json context when it is present.
- Treat Hermes as coordinator/router/supervisor, not as the owner of permanent template state.
- Preserve the review flow: gather/research, generate concepts, prepare previews, wait for approval, then execute/send/track.
- Do not create one-off hidden templates. Save reusable template decisions in human-readable files or dashboard state.
- If a needed niche template is missing, create a follow-up task to add it instead of improvising silently.

For every meaningful task, resolve project/domain context before dispatching. Never mix outreach/email context into game-dev tasks, and never mix game asset context into outreach tasks."""


NICHE_ALIASES = {
    "septic": ("septic", "septic tank", "drain field", "sewer line"),
    "portable-restrooms": ("portable restroom", "portable toilet", "porta potty", "porta john"),
    "tree-service": ("tree service", "tree company", "tree removal", "arborist", "storm damage"),
    "landscaping": ("landscaping", "landscaper", "lawn care", "hardscape"),
    "dumpster-rental": ("dumpster", "roll-off", "roll off", "construction debris"),
    "grease-trap": ("grease trap", "grease interceptor", "restaurant compliance", "fog compliance"),
    "estate-sales": ("estate sale", "estate liquidation", "downsizing", "appraisal"),
}


def _read_optional(path: Path, max_chars: int) -> str:
    try:
        return path.read_text(encoding="utf-8")[:max_chars]
    except OSError:
        return ""


def _detect_niches(text: str) -> list[str]:
    lower = text.lower()
    return [
        slug
        for slug, aliases in NICHE_ALIASES.items()
        if any(alias in lower for alias in aliases)
    ]


def _template_roots() -> list[Path]:
    return [
        settings.root / "repos" / "Pomely-native" / "dashboard" / "templates",
        Path("/opt/hermes-codex-ops/repos/Pomely-native/dashboard/templates"),
        Path("/Users/anthonylamentola/Pomely-native/dashboard/templates"),
    ]


def _repo_design_template_context(task: Task) -> dict:
    haystack = "\n".join(
        [
            task.summary,
            json.dumps(task.payload.get("project", {}), sort_keys=True),
            json.dumps(task.payload.get("task", {}), sort_keys=True),
            str(task.payload.get("instructions", "")),
        ]
    )
    niches = _detect_niches(haystack)
    if "outreach" in haystack.lower() or "simpleweb" in haystack.lower():
        for slug in ("septic", "portable-restrooms", "dumpster-rental", "grease-trap", "estate-sales"):
            if slug not in niches:
                niches.append(slug)

    for root in _template_roots():
        if not root.exists():
            continue
        sections = []
        global_design = _read_optional(root / "DESIGN.md", 5000)
        playbook = _read_optional(root / "niches" / "README.md", 3500)
        if global_design:
            sections.append(f"# Global Design Rules\n{global_design}")
        if playbook:
            sections.append(f"# Niche Template Playbook\n{playbook}")
        for slug in niches[:4]:
            niche_root = root / "niches" / slug
            parts = [
                _read_optional(niche_root / "DESIGN.md", 2500),
                _read_optional(niche_root / "SKILL.md", 2500),
                _read_optional(niche_root / "niche.json", 2000),
            ]
            body = "\n\n".join(part for part in parts if part.strip())
            if body:
                sections.append(f"## Niche: {slug}\n{body}")
        if sections:
            return {
                "source": "vps-repo-owned-design-templates",
                "detectedNiches": niches,
                "templateRoot": str(root),
                "body": "\n\n---\n\n".join(sections),
            }
    return {}


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
        route_packet = ContextRouter(memory=self.memory, audit=self.audit).resolve(
            f"{task.summary}\n{json.dumps(task.payload, sort_keys=True)}",
            project_id=(task.payload.get("dashboard") or {}).get("project_id")
            if isinstance(task.payload.get("dashboard"), dict)
            else None,
        )
        route_context = context_packet_to_markdown(route_packet)
        design_context = task.payload.get("design_template_context") or _repo_design_template_context(task)
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
        relevant_memory = "\n\n".join([relevant_memory, route_context])
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
