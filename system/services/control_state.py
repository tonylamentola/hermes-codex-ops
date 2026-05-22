from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from system.services.audit_log import AuditLog, utc_now
from system.services.settings import settings


DEFAULT_STATE = {
    "paused": False,
    "reason": "",
    "updated_at": "",
    "updated_by": "",
}


@dataclass
class ControlState:
    path: Path
    audit: AuditLog

    @classmethod
    def create(cls) -> "ControlState":
        return cls(path=settings.root / "config" / "control-state.json", audit=AuditLog())

    def read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {**DEFAULT_STATE, "updated_at": utc_now()}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def write(self, state: dict[str, Any]) -> dict[str, Any]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return state

    def pause(self, *, reason: str = "", updated_by: str = "operator") -> dict[str, Any]:
        state = {
            "paused": True,
            "reason": reason,
            "updated_at": utc_now(),
            "updated_by": updated_by,
        }
        self.write(state)
        self.audit.write(agent="control-state", action="pause", result="ok", reason=reason, updated_by=updated_by)
        return state

    def resume(self, *, updated_by: str = "operator") -> dict[str, Any]:
        state = {
            "paused": False,
            "reason": "",
            "updated_at": utc_now(),
            "updated_by": updated_by,
        }
        self.write(state)
        self.audit.write(agent="control-state", action="resume", result="ok", updated_by=updated_by)
        return state

    def is_paused(self) -> bool:
        return bool(self.read().get("paused", False))
