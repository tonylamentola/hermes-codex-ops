from __future__ import annotations

import argparse
import json

from system.services.audit_log import AuditLog
from system.services.context_router import ContextRouter, context_packet_to_markdown
from system.services.memory import MemoryStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve project/domain context before Codex work.")
    parser.add_argument("request", help="Natural-language task/request to route")
    parser.add_argument("--project-id", default=None, help="Force or hint a project id")
    parser.add_argument("--json", action="store_true", help="Print raw JSON context packet")
    args = parser.parse_args()

    packet = ContextRouter(memory=MemoryStore(), audit=AuditLog()).resolve(
        args.request,
        project_id=args.project_id,
    )
    print(json.dumps(packet, indent=2, sort_keys=True) if args.json else context_packet_to_markdown(packet))


if __name__ == "__main__":
    main()
