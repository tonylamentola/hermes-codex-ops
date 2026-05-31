from __future__ import annotations

import json
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from system.services.settings import settings


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class AuditLog:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or settings.log_path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(
        self,
        *,
        agent: str,
        action: str,
        result: str,
        error: str | None = None,
        **details: Any,
    ) -> dict[str, Any]:
        record = {
            "timestamp": utc_now(),
            "agent": agent,
            "action": action,
            "result": result,
            **details,
        }
        if error:
            record["error"] = error
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
        return record

    def tail(self, limit: int = 20) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as handle:
            lines = list(deque(handle, maxlen=max(0, int(limit))))
        return [json.loads(line) for line in lines if line.strip()]
