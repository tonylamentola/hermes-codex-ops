from __future__ import annotations

import argparse
import asyncio
import json

from system.hermes.coordinator import HermesCoordinator
from system.services.context_router import ContextRouter, context_packet_to_markdown
from system.services.audit_log import AuditLog
from system.services.memory import MemoryStore
from system.services.queue import TaskQueue


async def main() -> None:
    parser = argparse.ArgumentParser(description="Hermes coordinator CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    submit = sub.add_parser("submit")
    submit.add_argument("summary")
    submit.add_argument("--priority", type=int, default=5)
    submit.add_argument("--agent", default="codex")
    submit.add_argument("--decompose", action="store_true")
    sub.add_parser("status")
    sub.add_parser("audit-capabilities")
    plan = sub.add_parser("plan")
    plan.add_argument("summary")
    plan.add_argument("--priority", type=int, default=5)
    plan.add_argument("--enqueue", action="store_true")
    context = sub.add_parser("context")
    context.add_argument("task_id")
    resolve = sub.add_parser("resolve")
    resolve.add_argument("request")
    resolve.add_argument("--project-id", default=None)
    resolve.add_argument("--json", action="store_true")
    args = parser.parse_args()

    hermes = HermesCoordinator.create()
    MemoryStore().ensure_baseline()
    TaskQueue().export_json()

    if args.command == "submit":
        task = await hermes.submit_task(
            args.summary,
            priority=args.priority,
            assigned_agent=args.agent,
            decompose=args.decompose,
        )
        print(task.id)
    elif args.command == "status":
        print(hermes.status())
    elif args.command == "audit-capabilities":
        print(json.dumps(hermes.audit_capabilities(), indent=2, sort_keys=True))
    elif args.command == "plan":
        if args.enqueue:
            task = await hermes.submit_task(args.summary, priority=args.priority, decompose=True)
            print(json.dumps({"root_task_id": task.id, "subtasks": hermes.plan_subtasks(args.summary, priority=args.priority)}, indent=2, sort_keys=True))
        else:
            print(json.dumps(hermes.plan_subtasks(args.summary, priority=args.priority), indent=2, sort_keys=True))
    elif args.command == "context":
        print(await hermes.prepare_worker_context(args.task_id))
    elif args.command == "resolve":
        packet = ContextRouter(memory=MemoryStore(), audit=AuditLog()).resolve(args.request, project_id=args.project_id)
        print(json.dumps(packet, indent=2, sort_keys=True) if args.json else context_packet_to_markdown(packet))

    AuditLog().write(agent="hermes-cli", action=args.command, result="ok")


if __name__ == "__main__":
    asyncio.run(main())
