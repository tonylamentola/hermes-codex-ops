from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class Capability:
    name: str
    expected: str
    current: str
    status: str
    action: str


@dataclass(frozen=True)
class PlannedSubtask:
    summary: str
    assigned_agent: str
    priority: int
    reason: str


class CapabilityPlanner:
    """Small, inspectable planner for Hermes coordination work.

    This is deliberately rules-based. Hermes can later swap in a richer agent
    planner, but the durable queue should already express decomposition,
    delegation, and improvement tasks without hiding state in prompts.
    """

    DEFAULT_AGENTS = {
        "research": "codex-research",
        "implementation": "codex-implementation",
        "verification": "codex-verification",
        "documentation": "codex-docs",
        "improvement": "codex-improvement",
    }

    def audit(self) -> list[dict[str, str]]:
        capabilities = [
            Capability(
                name="Context routing",
                expected="Resolve project/domain context before meaningful work.",
                current="Implemented through ContextRouter and worker context packets.",
                status="available",
                action="Keep context-routing.json current and run hermes context/resolve before dispatch.",
            ),
            Capability(
                name="Durable task queue",
                expected="Persist queue state, retries, approvals, and exports.",
                current="Implemented through SQLite plus tasks/*.json exports.",
                status="available",
                action="Use queued tasks as the source of truth instead of chat-only instructions.",
            ),
            Capability(
                name="Multi-agent delegation",
                expected="Split broad work into named lanes that can be worked independently.",
                current="Previously collapsed all pending tasks into one codex lane.",
                status="enabled-by-this-repo",
                action="Use `plan --enqueue` or `/plan` and run workers with --agent for each lane.",
            ),
            Capability(
                name="Self-improvement loop",
                expected="Capture repeated gaps and create skill/process improvement tasks.",
                current="Previously only appended memory notes.",
                status="enabled-by-this-repo",
                action="Use improvement subtasks and agent-status memory to turn gaps into explicit skill/doc tasks.",
            ),
            Capability(
                name="Skill creation",
                expected="Create reusable operational skills when a task reveals repeatable workflow.",
                current="No native skill generator exists in this repo.",
                status="partially-available",
                action="Queue codex-improvement tasks that create or update AGENTS.md, SKILL.md, or docs.",
            ),
            Capability(
                name="Provider proxy / public Hermes Agent runtime",
                expected="Use public Hermes Agent features such as proxy, plugins, Curator, and native subagents.",
                current="This repo is a custom Codex ops layer, not the Nous Hermes Agent runtime.",
                status="external",
                action="Install/configure hermes-agent separately if those runtime features are required.",
            ),
        ]
        return [asdict(item) for item in capabilities]

    def plan(self, summary: str, *, priority: int = 5, payload: dict[str, Any] | None = None) -> list[PlannedSubtask]:
        text = f"{summary}\n{payload or {}}".lower()
        broad = any(
            marker in text
            for marker in (
                "audit",
                "research",
                "implement",
                "build",
                "fix",
                "multi-agent",
                "multiple agent",
                "self improve",
                "skill",
                "workflow",
                "system",
                "setup",
            )
        )
        if not broad:
            return []

        subtasks: list[PlannedSubtask] = []
        if any(marker in text for marker in ("research", "audit", "offerings", "compare", "setup", "system")):
            subtasks.append(
                PlannedSubtask(
                    summary=f"Research and audit context for: {summary}",
                    assigned_agent=self.DEFAULT_AGENTS["research"],
                    priority=priority + 1,
                    reason="Establish intended behavior and current gaps before implementation.",
                )
            )
        if any(marker in text for marker in ("implement", "build", "fix", "change", "setup", "leverage")):
            subtasks.append(
                PlannedSubtask(
                    summary=f"Implement scoped changes for: {summary}",
                    assigned_agent=self.DEFAULT_AGENTS["implementation"],
                    priority=priority,
                    reason="Make the concrete repository or configuration changes.",
                )
            )
        subtasks.append(
            PlannedSubtask(
                summary=f"Verify and report results for: {summary}",
                assigned_agent=self.DEFAULT_AGENTS["verification"],
                priority=max(priority - 1, 1),
                reason="Run checks and summarize residual risks.",
            )
        )
        if any(marker in text for marker in ("skill", "self improve", "repeatable", "workflow", "hermes")):
            subtasks.append(
                PlannedSubtask(
                    summary=f"Create or update reusable Hermes skill/process guidance for: {summary}",
                    assigned_agent=self.DEFAULT_AGENTS["improvement"],
                    priority=max(priority - 1, 1),
                    reason="Convert the learned workflow into durable reusable guidance.",
                )
            )
        return subtasks
