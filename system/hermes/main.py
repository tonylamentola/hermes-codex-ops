from __future__ import annotations

import argparse
import asyncio

from system.hermes.coordinator import HermesCoordinator
from system.services.audit_log import AuditLog
from system.services.memory import MemoryStore
from system.services.queue import TaskQueue


async def main() -> None:
    parser = argparse.ArgumentParser(description="Hermes coordinator CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    submit = sub.add_parser("submit")
    submit.add_argument("summary")
    submit.add_argument("--priority", type=int, default=5)
    sub.add_parser("status")
    context = sub.add_parser("context")
    context.add_argument("task_id")
    args = parser.parse_args()

    hermes = HermesCoordinator.create()
    MemoryStore().ensure_baseline()
    TaskQueue().export_json()

    if args.command == "submit":
        task = await hermes.submit_task(args.summary, priority=args.priority)
        print(task.id)
    elif args.command == "status":
        print(hermes.status())
    elif args.command == "context":
        print(await hermes.prepare_worker_context(args.task_id))

    AuditLog().write(agent="hermes-cli", action=args.command, result="ok")


if __name__ == "__main__":
    asyncio.run(main())
