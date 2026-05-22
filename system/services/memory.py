from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from system.services.audit_log import utc_now
from system.services.settings import settings


class MemoryStore:
    """Human-readable memory store backed by Markdown and JSON files."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or settings.root / "memory"
        self.root.mkdir(parents=True, exist_ok=True)

    def ensure_baseline(self) -> None:
        for folder in ("projects", "agents", "deployments", "clients", "logs", "summaries"):
            (self.root / folder).mkdir(parents=True, exist_ok=True)
        defaults = {
            "active-projects.md": "# Active Projects\n\n",
            "deployment-history.md": "# Deployment History\n\n",
            "github-state.md": "# GitHub State\n\n",
            "agent-status.md": "# Agent Status\n\n",
            "summaries/handoffs.md": "# Handoff Summaries\n\n",
        }
        for relative, content in defaults.items():
            path = self.root / relative
            if not path.exists():
                path.write_text(content, encoding="utf-8")

    def append_markdown(self, relative_path: str, heading: str, body: str) -> Path:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = f"\n## {utc_now()} - {heading}\n\n{body.strip()}\n"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(entry)
        return path

    def read_markdown(self, relative_path: str, max_chars: int = 4000) -> str:
        path = self.root / relative_path
        if not path.exists():
            return ""
        text = path.read_text(encoding="utf-8")
        return text[-max_chars:]

    def read_full_markdown(self, relative_path: str) -> str:
        path = self.root / relative_path
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def write_json_state(self, relative_path: str, data: dict[str, Any]) -> Path:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        envelope = {"updated_at": utc_now(), "data": data}
        path.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def read_json_state(self, relative_path: str) -> dict[str, Any]:
        path = self.root / relative_path
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))
