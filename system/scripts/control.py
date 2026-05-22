from __future__ import annotations

import argparse
import json

from system.services.control_state import ControlState
from system.services.queue import TaskQueue


def main() -> None:
    parser = argparse.ArgumentParser(description="Operator controls for Hermes Codex Ops")
    sub = parser.add_subparsers(dest="command", required=True)
    pause = sub.add_parser("pause")
    pause.add_argument("reason", nargs="*", default=[])
    sub.add_parser("resume")
    sub.add_parser("status")
    cancel = sub.add_parser("cancel")
    cancel.add_argument("task_id")
    approve = sub.add_parser("approve")
    approve.add_argument("task_id")
    args = parser.parse_args()

    control = ControlState.create()
    queue = TaskQueue()
    if args.command == "pause":
        print(json.dumps(control.pause(reason=" ".join(args.reason), updated_by="cli"), indent=2))
    elif args.command == "resume":
        print(json.dumps(control.resume(updated_by="cli"), indent=2))
    elif args.command == "status":
        print(json.dumps(control.read(), indent=2))
    elif args.command == "cancel":
        print(json.dumps(queue.update_status(args.task_id, "cancelled").__dict__, indent=2, sort_keys=True))
    elif args.command == "approve":
        task = queue.get(args.task_id)
        if not task:
            raise SystemExit(f"Unknown task: {args.task_id}")
        payload = dict(task.payload)
        payload["approved"] = True
        payload["approved_by"] = "cli"
        queue.update_payload(task.id, payload)
        print(json.dumps(queue.update_status(task.id, "pending").__dict__, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
