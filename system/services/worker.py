from __future__ import annotations

import asyncio
from dataclasses import dataclass

from system.hermes.coordinator import HermesCoordinator
from system.services.ai_backend import CodexBackend, CodexCliBackend, DryRunBackend
from system.services.audit_log import AuditLog
from system.services.control_state import ControlState
from system.services.memory import MemoryStore
from system.services.notifier import TelegramNotifier
from system.services.queue import Task, TaskQueue
from system.services.settings import settings


def choose_backend():
    if settings.worker_backend in {"codex-api", "codex"}:
        return CodexBackend()
    if settings.worker_backend == "codex-cli":
        return CodexCliBackend()
    return DryRunBackend()


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
            await self.notifier.send(f"Task awaiting approval: {task.id}\n{task.summary}")
            return awaiting

        self.audit.write(agent="worker", action="claim", result="active", task_id=task.id)
        await self.notifier.send(f"Task started: {task.id}\n{task.summary}")
        try:
            worker_context = await self.hermes.prepare_worker_context(task.id)
            payload = dict(task.payload)
            payload["worker_context"] = worker_context
            payload["backend"] = self.hermes.backend.name
            self.queue.update_payload(task.id, payload)
            completed = self.queue.update_status(task.id, "completed")
            self.memory.append_markdown(
                "summaries/handoffs.md",
                "Task completed",
                f"- Task: `{completed.id}`\n- Summary: {completed.summary}\n- Backend: {self.hermes.backend.name}\n\n{worker_context[:2000]}",
            )
            self.audit.write(agent="worker", action="complete", result="ok", task_id=task.id)
            await self.notifier.send(f"Task completed: {task.id}\n{task.summary}")
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
            await self.notifier.send(message)
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
