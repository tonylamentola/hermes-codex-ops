from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from system.hermes.coordinator import HermesCoordinator
from system.services.ai_backend import CodexBackend, CodexCliBackend, DryRunBackend
from system.services.audit_log import AuditLog
from system.services.control_state import ControlState
from system.services.memory import MemoryStore
from system.services.notifier import TelegramNotifier
from system.services.queue import Task, TaskQueue
from system.services.settings import settings

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
ARTIFACT_EXTENSIONS = IMAGE_EXTENSIONS | {".svg", ".pdf", ".zip", ".json", ".md", ".txt"}
AUTO_SEND_EXTENSIONS = IMAGE_EXTENSIONS | {".svg", ".pdf", ".zip", ".txt"}
PATH_ANCHORS = {"artifacts", "assets", "outputs", "output", "public", "dist", "build"}
AUTO_SEND_ARTIFACT_LIMIT = 5
WORKER_EXECUTION_SYSTEM = """You are Codex executing a Hermes worker task.
Use the provided WORKER_CONTEXT as operational context, then complete the task.
Return a concise result for the operator. If you create or identify deliverables,
include only the final deliverable paths, not every context file you inspected."""


def choose_backend():
    if settings.worker_backend in {"codex-api", "codex"}:
        return CodexBackend()
    if settings.worker_backend == "codex-cli":
        return CodexCliBackend()
    return DryRunBackend()


def task_chat_ids(task: Task) -> set[int] | None:
    telegram = task.payload.get("telegram")
    if not isinstance(telegram, dict):
        return None
    chat_id = telegram.get("chat_id")
    if chat_id is None:
        return None
    try:
        return {int(chat_id)}
    except (TypeError, ValueError):
        return None


def short_task_id(task: Task) -> str:
    return task.id[:8]


def _artifact_search_roots(root: Path) -> list[Path]:
    roots = [root]
    try:
        from system.services.context_router import load_routing_manifest

        for item in load_routing_manifest().get("projects", []):
            for key in ("repoCachePath", "repo_cache_path", "workspacePath", "workspace_path"):
                raw = str(item.get(key) or "")
                if not raw:
                    continue
                path = Path(raw)
                roots.append(path if path.is_absolute() else root / path)
    except (OSError, ValueError, TypeError):
        pass
    seen: set[str] = set()
    unique: list[Path] = []
    for path in roots:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _candidate_suffixes(candidate: str) -> list[Path]:
    normalized = candidate.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part and not part.endswith(":")]
    suffixes: list[Path] = []
    for index, part in enumerate(parts):
        if part.lower() in PATH_ANCHORS:
            suffixes.append(Path(*parts[index:]))
    if parts:
        suffixes.append(Path(parts[-1]))
    return suffixes


def _resolve_artifact_path(candidate: str, roots: list[Path]) -> Path:
    normalized = candidate.replace("\\", "/")
    path = Path(normalized)
    if path.is_absolute() and path.exists():
        return path
    search_paths: list[Path] = []
    if not path.is_absolute():
        search_paths.extend(root / path for root in roots)
    for suffix in _candidate_suffixes(candidate):
        search_paths.extend(root / suffix for root in roots)
    for search_path in search_paths:
        if search_path.exists():
            return search_path
    return path if path.is_absolute() else roots[0] / path


def extract_artifacts(text: str, *, root: Path | None = None) -> list[dict[str, Any]]:
    root = root or settings.root
    roots = _artifact_search_roots(root)
    candidates = set()
    candidates.update(re.findall(r"`([^`]+)`", text))
    candidates.update(re.findall(r"([A-Za-z]:\\[A-Za-z0-9_.:\\\\ -]+)", text))
    candidates.update(re.findall(r"(/[A-Za-z0-9._~:/?#@!$&'()*+,;=% -]+)", text))
    candidates.update(re.findall(r"([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_. -]+)+)", text))

    artifacts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in candidates:
        candidate = raw.strip().strip(".,:;)")
        if not candidate:
            continue
        path = Path(candidate.replace("\\", "/"))
        if path.suffix.lower() not in ARTIFACT_EXTENSIONS:
            continue
        resolved = _resolve_artifact_path(candidate, roots)
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        artifacts.append(
            {
                "path": str(resolved),
                "display_path": candidate,
                "exists": resolved.exists(),
                "kind": "image" if resolved.suffix.lower() in IMAGE_EXTENSIONS else "file",
            }
        )
    return sorted(artifacts, key=lambda item: (not item["exists"], item["path"]))


def artifact_summary(artifacts: list[dict[str, Any]]) -> str:
    if not artifacts:
        return "Artifacts: none reported."
    lines = ["Artifacts:"]
    for artifact in artifacts[:8]:
        marker = "ok" if artifact["exists"] else "missing"
        lines.append(f"- {marker}: {artifact['display_path']}")
    return "\n".join(lines)


def auto_send_artifacts(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sendable = [
        artifact
        for artifact in artifacts
        if artifact.get("exists") and Path(str(artifact.get("path", ""))).suffix.lower() in AUTO_SEND_EXTENSIONS
    ]
    return sorted(
        sendable,
        key=lambda item: (
            0 if item.get("kind") == "image" else 1,
            str(item.get("path", "")),
        ),
    )[:AUTO_SEND_ARTIFACT_LIMIT]


@dataclass
class Worker:
    queue: TaskQueue
    memory: MemoryStore
    audit: AuditLog
    notifier: TelegramNotifier
    hermes: HermesCoordinator
    control: ControlState
    assigned_agent: str = "codex"

    @classmethod
    def create(cls, *, assigned_agent: str = "codex") -> "Worker":
        audit = AuditLog()
        queue = TaskQueue()
        memory = MemoryStore()
        backend = choose_backend()
        hermes = HermesCoordinator(queue=queue, memory=memory, audit=audit, backend=backend)
        return cls(
            queue=queue,
            memory=memory,
            audit=audit,
            notifier=TelegramNotifier(audit),
            hermes=hermes,
            control=ControlState.create(),
            assigned_agent=assigned_agent,
        )

    async def run_once(self) -> Task | None:
        if self.control.is_paused():
            self.audit.write(agent="worker", action="poll", result="paused")
            return None

        task = self.queue.claim_next(assigned_agent=self.assigned_agent)
        if not task:
            self.audit.write(agent="worker", action="poll", result="idle")
            return None

        if settings.worker_require_approval and not task.payload.get("approved"):
            payload = dict(task.payload)
            payload["approval_required"] = True
            self.queue.update_payload(task.id, payload)
            awaiting = self.queue.update_status(task.id, "awaiting_approval")
            self.audit.write(agent="worker", action="approval_required", result="awaiting_approval", task_id=task.id)
            await self.notifier.send(
                f"Task awaiting approval: {short_task_id(awaiting)}\n{awaiting.summary}\nUse /approve {awaiting.id} to run it.",
                chat_ids=task_chat_ids(awaiting),
            )
            return awaiting

        self.audit.write(agent="worker", action="claim", result="active", task_id=task.id, assigned_agent=self.assigned_agent)
        await self.notifier.send(
            f"Task started: {short_task_id(task)}\n{task.summary}",
            chat_ids=task_chat_ids(task),
        )
        try:
            worker_context = await self.hermes.prepare_worker_context(task.id)
            worker_result = await self.hermes.backend.complete(
                worker_context,
                system=WORKER_EXECUTION_SYSTEM,
            )
            payload = dict(task.payload)
            payload["worker_context"] = worker_context
            payload["worker_result"] = worker_result
            payload["backend"] = self.hermes.backend.name
            payload["artifacts"] = extract_artifacts(worker_result)
            self.queue.update_payload(task.id, payload)
            completed = self.queue.update_status(task.id, "completed")
            self.memory.append_markdown(
                "summaries/handoffs.md",
                "Task completed",
                f"- Task: `{completed.id}`\n- Summary: {completed.summary}\n- Backend: {self.hermes.backend.name}\n\n{worker_result[:2000]}",
            )
            self.audit.write(agent="worker", action="complete", result="ok", task_id=task.id)
            sendable = auto_send_artifacts(completed.payload.get("artifacts", []))
            if sendable:
                artifact_note = f"Sending {len(sendable)} artifact file(s) now."
            elif completed.payload.get("artifacts"):
                artifact_note = "I found artifact paths, but no Telegram-sendable files."
            else:
                artifact_note = worker_result[:1500]
            completion_message = (
                f"Task completed: {short_task_id(completed)}\n{completed.summary}\n\n"
                f"{artifact_note}\n\n"
                f"Use /task {completed.id} for details."
            )
            await self.notifier.send(
                completion_message,
                chat_ids=task_chat_ids(completed),
            )
            for artifact in sendable:
                await self.notifier.send_file(
                    artifact["path"],
                    caption=f"Artifact for {short_task_id(completed)}: {artifact['display_path']}",
                    chat_ids=task_chat_ids(completed),
                )
            return completed
        except Exception as exc:
            fresh = self.queue.get(task.id)
            retry_count = fresh.retry_count if fresh else task.retry_count
            if retry_count + 1 <= settings.worker_max_retries:
                failed = self.queue.update_status(task.id, "pending", retry_increment=True)
                result = "retry_scheduled"
                message = f"Task failed; retry scheduled ({failed.retry_count}/{settings.worker_max_retries}): {task.id}\n{exc}"
            else:
                failed = self.queue.update_status(task.id, "failed")
                result = "failed"
                message = f"Task failed permanently: {task.id}\n{exc}"
            self.memory.append_markdown(
                "agent-status.md",
                "Worker task failure",
                f"- Task: `{task.id}`\n- Result: {result}\n- Error: `{exc}`",
            )
            self.audit.write(agent="worker", action="process", result=result, task_id=task.id, error=str(exc))
            await self.notifier.send(message, chat_ids=task_chat_ids(failed))
            return failed

    async def run_forever(self) -> None:
        self.memory.ensure_baseline()
        self.audit.write(agent="worker", action="start", result="ok", backend=self.hermes.backend.name, assigned_agent=self.assigned_agent)
        while True:
            await self.run_once()
            await asyncio.sleep(settings.worker_poll_seconds)


async def main_async(*, once: bool = False, assigned_agent: str = "codex") -> None:
    worker = Worker.create(assigned_agent=assigned_agent)
    if once:
        await worker.run_once()
    else:
        await worker.run_forever()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Durable Codex worker loop")
    parser.add_argument("--once", action="store_true", help="Process at most one pending task and exit")
    parser.add_argument("--agent", default="codex", help="Assigned-agent lane to claim from")
    args = parser.parse_args()
    asyncio.run(main_async(once=args.once, assigned_agent=args.agent))


if __name__ == "__main__":
    main()
