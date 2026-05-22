from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from system.hermes.coordinator import HermesCoordinator
from system.services.control_state import ControlState
from system.services.settings import settings


def exists(path: Path) -> str:
    return "ok" if path.exists() else "missing"


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect Hermes Codex Ops health")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args()

    root = settings.root
    status = HermesCoordinator.create().status()
    control = ControlState.create().read()
    report = {
        "root": str(root),
        "queue": status["queue"],
        "control": control,
        "files": {
            "env": exists(root / ".env"),
            "repos_config": exists(root / "config" / "repos.json"),
            "control_state": exists(root / "config" / "control-state.json"),
            "queue_db": exists(settings.database_path),
            "audit_log": exists(settings.log_path),
            "context_pack": exists(root / "memory" / "summaries" / "context-pack.md"),
        },
        "executables": {
            "codex": "ok" if shutil.which("codex") else "missing",
        },
        "recent_logs": status["recent_logs"],
    }

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return

    print(f"Root: {report['root']}")
    print(f"Queue: {report['queue']}")
    print(f"Paused: {control.get('paused')} {control.get('reason', '')}")
    print("Files:")
    for name, state in report["files"].items():
        print(f"  {name}: {state}")
    print("Executables:")
    for name, state in report["executables"].items():
        print(f"  {name}: {state}")
    print("Recent logs:")
    for row in report["recent_logs"]:
        print(f"  {row.get('timestamp')} {row.get('agent')} {row.get('action')} {row.get('result')}")


if __name__ == "__main__":
    main()
