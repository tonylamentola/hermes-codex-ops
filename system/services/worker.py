from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from system.hermes.coordinator import HERMES_SYSTEM_PROMPT, HermesCoordinator
from system.services.ai_backend import CodexBackend, CodexCliBackend, DryRunBackend
from system.services.audit_log import AuditLog
from system.services.control_state import ControlState
from system.services.memory import MemoryStore
from system.services.notifier import TelegramNotifier
from system.services.queue import Task, TaskQueue
from system.services.settings import settings

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
ARTIFACT_EXTENSIONS = IMAGE_EXTENSIONS | {".svg", ".pdf", ".zip", ".json", ".md", ".txt"}


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


def extract_artifacts(text: str, *, root: Path | None = None) -> list[dict[str, Any]]:
    root = root or settings.root
    candidates = set()
    candidates.update(re.findall(r"`([^`]+)`", text))
    candidates.update(re.findall(r"(/[A-Za-z0-9._~:/?#@!$&'()*+,;=% -]+)", text))
    candidates.update(re.findall(r"([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_. -]+)+)", text))

    artifacts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in candidates:
        candidate = raw.strip().strip(".,:;)")
        if not candidate:
            continue
        path = Path(candidate)
        if path.suffix.lower() not in ARTIFACT_EXTENSIONS:
            continue
        resolved = path if path.is_absolute() else root / path
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


def expected_artifacts(payload: dict[str, Any], task_id: str, *, root: Path | None = None) -> list[dict[str, Any]]:
    root = root or settings.root
    expected: list[dict[str, Any]] = []
    for artifact in payload.get("artifacts", []):
        if not isinstance(artifact, dict):
            continue
        raw = str(artifact.get("display_path") or artifact.get("path") or "")
        if not raw:
            continue
        expanded = raw.replace("<task_id>", task_id)
        if "<task_id>" not in raw and not expanded.startswith("artifacts/"):
            continue
        path = Path(expanded)
        resolved = path if path.is_absolute() else root / path
        expected.append(
            {
                "path": str(resolved),
                "display_path": expanded,
                "exists": resolved.exists(),
                "kind": "image" if resolved.suffix.lower() in IMAGE_EXTENSIONS else "file",
                "required": True,
            }
        )
    return expected


def merge_artifacts(*artifact_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for artifacts in artifact_groups:
        for artifact in artifacts:
            path = artifact.get("path")
            if not path:
                continue
            current = merged.get(path, {})
            merged[path] = {**current, **artifact}
    return sorted(merged.values(), key=lambda item: (not item.get("exists", False), item.get("path", "")))


def missing_required_artifacts(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [artifact for artifact in artifacts if artifact.get("required") and not artifact.get("exists")]


def backend_prompt(worker_context: str, required_artifacts: list[dict[str, Any]]) -> str:
    sections = [worker_context]
    if required_artifacts:
        required_lines = "\n".join(f"- {artifact['display_path']}" for artifact in required_artifacts)
        sections.append(
            "REQUIRED OUTPUT FILES\n"
            "You are running from the operations repository root. Create every file below before you finish. "
            "Use mkdir -p for parent directories as needed. Do not merely describe the files.\n"
            f"{required_lines}\n\n"
            "After writing the files, reply with the artifact paths and a concise completion summary."
        )
    sections.append(
        "DASHBOARD TASK LEDGER\n"
        "At the end of your response, include one fenced JSON block labeled DASHBOARD_TASK_UPDATES. "
        "Use it to record work discovered or decomposed during execution so the Command Center can keep tracking it.\n"
        "Schema:\n"
        "```json\n"
        "{\n"
        '  "subtasks": [\n'
        '    {"text": "Completed step", "priority": "green", "status": "completed", "result": "What happened"}\n'
        "  ],\n"
        '  "followUpTasks": [\n'
        '    {"text": "Next task to queue", "priority": "yellow", "estimatedCost": 0.05, "instructions": "How to execute it"}\n'
        "  ]\n"
        "}\n"
        "```\n"
        "Use empty arrays when there are no subtasks or follow-ups. Do not include secrets."
    )
    return "\n\n".join(sections)


def extract_dashboard_task_updates(text: str) -> dict[str, list[dict[str, Any]]]:
    candidates = []
    labeled = re.search(
        r"DASHBOARD_TASK_UPDATES[\s:]*```(?:json)?\s*(\{[\s\S]*?\})\s*```",
        text,
        flags=re.IGNORECASE,
    )
    if labeled:
        candidates.append(labeled.group(1))
    candidates.extend(re.findall(r"```json\s*(\{[\s\S]*?\"(?:subtasks|followUpTasks)\"[\s\S]*?\})\s*```", text))
    candidates.extend(re.findall(r"(\{[\s\S]*?\"(?:subtasks|followUpTasks)\"[\s\S]*?\})", text))

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return {
                "subtasks": parsed.get("subtasks") if isinstance(parsed.get("subtasks"), list) else [],
                "followUpTasks": parsed.get("followUpTasks")
                if isinstance(parsed.get("followUpTasks"), list)
                else [],
            }
    return {"subtasks": [], "followUpTasks": []}


async def post_dashboard_callback(
    task: Task,
    *,
    status: str,
    summary: str,
    result: str = "",
    task_updates: dict[str, list[dict[str, Any]]] | None = None,
) -> None:
    dashboard = task.payload.get("dashboard")
    if not isinstance(dashboard, dict):
        return
    callback_url = str(dashboard.get("callback_url") or "").strip()
    if not callback_url:
        return

    payload = {
        "projectId": dashboard.get("project_id"),
        "taskId": dashboard.get("task_id"),
        "status": status,
        "summary": summary,
        "result": result,
        "secret": dashboard.get("callback_secret"),
        "notes": [f"Hermes task `{task.id}` updated dashboard task `{dashboard.get('task_id')}`."],
    }
    if task_updates:
        payload["subtasks"] = task_updates.get("subtasks", [])
        payload["followUpTasks"] = task_updates.get("followUpTasks", [])
    try:
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(callback_url, json=payload)
            response.raise_for_status()
    except Exception as exc:
        AuditLog().write(
            agent="worker",
            action="dashboard_callback",
            result="failed",
            task_id=task.id,
            error=str(exc),
        )


@dataclass
class Worker:
    queue: TaskQueue
    memory: MemoryStore
    audit: AuditLog
    notifier: TelegramNotifier
    hermes: HermesCoordinator
    control: ControlState

    @classmethod
    def create(cls) -> "Worker":
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
        )

    async def run_once(self) -> Task | None:
        if self.control.is_paused():
            self.audit.write(agent="worker", action="poll", result="paused")
            return None

        task = self.queue.claim_next(assigned_agent="codex")
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

        self.audit.write(agent="worker", action="claim", result="active", task_id=task.id)
        await post_dashboard_callback(
            task,
            status="running",
            summary=f"Hermes started task {short_task_id(task)}.",
        )
        await self.notifier.send(
            f"Task started: {short_task_id(task)}\n{task.summary}",
            chat_ids=task_chat_ids(task),
        )
        try:
            worker_context = await self.hermes.prepare_worker_context(task.id)
            required_artifacts = expected_artifacts(task.payload, task.id)
            self.audit.write(agent="worker", action="backend_start", result="started", task_id=task.id)
            worker_result = await self.hermes.backend.complete(
                backend_prompt(worker_context, required_artifacts),
                system=HERMES_SYSTEM_PROMPT,
            )
            result_artifacts = extract_artifacts(worker_result)
            artifacts = merge_artifacts(result_artifacts, required_artifacts)
            payload = dict(task.payload)
            payload["worker_context"] = worker_context
            payload["worker_result"] = worker_result
            payload["backend"] = self.hermes.backend.name
            payload["artifacts"] = artifacts
            self.queue.update_payload(task.id, payload)
            missing = missing_required_artifacts(artifacts)
            if missing:
                missing_paths = ", ".join(item["display_path"] for item in missing)
                raise RuntimeError(f"Required artifact(s) missing after backend run: {missing_paths}")
            completed = self.queue.update_status(task.id, "completed")
            self.memory.append_markdown(
                "summaries/handoffs.md",
                "Task completed",
                f"- Task: `{completed.id}`\n- Summary: {completed.summary}\n- Backend: {self.hermes.backend.name}\n\n{worker_result[:2000]}",
            )
            self.audit.write(agent="worker", action="complete", result="ok", task_id=task.id)
            task_updates = extract_dashboard_task_updates(worker_result)
            await post_dashboard_callback(
                completed,
                status="completed",
                summary=f"Hermes completed task {short_task_id(completed)}.",
                result=worker_result,
                task_updates=task_updates,
            )
            existing_artifacts = [
                artifact for artifact in completed.payload.get("artifacts", [])
                if artifact.get("exists")
            ]
            artifact_lines = "\n".join(
                f"- {artifact.get('display_path', artifact.get('path'))}"
                for artifact in existing_artifacts[:5]
            )
            completion_message = (
                f"Done: {short_task_id(completed)}\n"
                f"{completed.summary}\n\n"
                + (
                    f"Files ready:\n{artifact_lines}\n\nSay `latest result` and I’ll send them."
                    if existing_artifacts
                    else "No files were attached. Say `tasks` if you want to check the task list."
                )
            )
            await self.notifier.send(
                completion_message,
                chat_ids=task_chat_ids(completed),
            )
            for artifact in completed.payload.get("artifacts", [])[:3]:
                if artifact.get("exists") and artifact.get("kind") == "image":
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
                await post_dashboard_callback(
                    failed,
                    status="failed",
                    summary=f"Hermes task {short_task_id(failed)} failed.",
                    result=str(exc),
                )
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
        self.audit.write(agent="worker", action="start", result="ok", backend=self.hermes.backend.name)
        while True:
            await self.run_once()
            await asyncio.sleep(settings.worker_poll_seconds)


async def main_async(*, once: bool = False) -> None:
    worker = Worker.create()
    if once:
        await worker.run_once()
    else:
        await worker.run_forever()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Durable Codex worker loop")
    parser.add_argument("--once", action="store_true", help="Process at most one pending task and exit")
    args = parser.parse_args()
    asyncio.run(main_async(once=args.once))


if __name__ == "__main__":
    main()
