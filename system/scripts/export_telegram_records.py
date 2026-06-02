from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from system.services.settings import settings


@dataclass(frozen=True)
class ExportPaths:
    database_path: Path
    log_path: Path
    output_path: Path


def _parse_day(value: str | None) -> date:
    if not value:
        return datetime.now(UTC).date()
    return date.fromisoformat(value)


def _task_matches_chat(task: dict[str, Any], chat_id: int) -> bool:
    try:
        payload = json.loads(task["payload"])
    except (KeyError, TypeError, json.JSONDecodeError):
        return False
    telegram = payload.get("telegram")
    if not isinstance(telegram, dict):
        return False
    try:
        return int(telegram.get("chat_id")) == int(chat_id)
    except (TypeError, ValueError):
        return False


def _load_tasks(database_path: Path, chat_id: int, day: date) -> list[dict[str, Any]]:
    if not database_path.exists():
        return []
    start = day.isoformat()
    with sqlite3.connect(database_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, timestamp, updated_at, status, summary, payload
            FROM tasks
            WHERE substr(timestamp, 1, 10) = ?
            ORDER BY timestamp ASC
            """,
            (start,),
        ).fetchall()
    return [dict(row) for row in rows if _task_matches_chat(dict(row), chat_id)]


def _load_audit_events(log_path: Path, day: date, chat_id: int, task_ids: set[str]) -> list[dict[str, Any]]:
    if not log_path.exists():
        return []
    events: list[dict[str, Any]] = []
    prefix = day.isoformat()
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        timestamp = str(event.get("timestamp", ""))
        if not timestamp.startswith(prefix):
            continue
        event_chat_id = event.get("chat_id")
        event_task_id = event.get("task_id")
        try:
            matches_chat = event_chat_id is not None and int(event_chat_id) == int(chat_id)
        except (TypeError, ValueError):
            matches_chat = False
        if matches_chat or (event_task_id and event_task_id in task_ids):
            events.append(event)
    events.sort(key=lambda item: str(item.get("timestamp", "")))
    return events


def _payload_worker_result(payload_text: str, max_chars: int = 1200) -> str | None:
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        return None
    result = payload.get("worker_context")
    if not result:
        return None
    text = str(result).strip()
    return text[:max_chars] + ("..." if len(text) > max_chars else "")


def render_export(*, chat_id: int, day: date, tasks: list[dict[str, Any]], events: list[dict[str, Any]]) -> str:
    lines: list[str] = [
        "Hermes Telegram Conversation Export (Durable Records)",
        f"Date (UTC): {day.isoformat()}",
        f"Chat ID: {chat_id}",
        "",
        "Scope and limitation:",
        "- This export is generated from durable Hermes records: append-only logs and task queue state.",
        "- Raw Telegram message bodies are not persisted in current durable logs.",
        "- This file contains the auditable event timeline plus related task summaries/results.",
        "",
        "Today's Chat-Linked Tasks:",
    ]
    if tasks:
        for task in tasks:
            lines.append(
                f"- {task['id']} | status={task['status']} | summary={task['summary']}"
            )
    else:
        lines.append("- none")

    lines.extend(["", "Event Timeline (UTC):"])
    if events:
        for event in events:
            suffix = ""
            if event.get("task_id"):
                suffix += f" task_id={event['task_id']}"
            if event.get("sent") is not None:
                suffix += f" sent={event['sent']}"
            if event.get("error"):
                suffix += f" error={event['error']}"
            lines.append(
                f"- {event.get('timestamp')} | {event.get('agent')}.{event.get('action')} | "
                f"result={event.get('result')}{suffix}"
            )
    else:
        lines.append("- none")

    completed = [task for task in tasks if task.get("status") == "completed"]
    if completed:
        lines.extend(["", "Completed Task Result Previews:"])
        for task in completed:
            result = _payload_worker_result(str(task.get("payload", "")))
            if result:
                lines.append(f"\nTask {task['id']} result preview:\n{result}")

    return "\n".join(lines).rstrip() + "\n"


def export_chat_records(chat_id: int, day: date, paths: ExportPaths) -> Path:
    tasks = _load_tasks(paths.database_path, chat_id, day)
    task_ids = {str(task["id"]) for task in tasks}
    events = _load_audit_events(paths.log_path, day, chat_id, task_ids)
    paths.output_path.parent.mkdir(parents=True, exist_ok=True)
    paths.output_path.write_text(
        render_export(chat_id=chat_id, day=day, tasks=tasks, events=events),
        encoding="utf-8",
    )
    return paths.output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export durable Telegram/Hermes records for a chat.")
    parser.add_argument("--chat-id", type=int, required=True)
    parser.add_argument("--date", default=None, help="UTC date in YYYY-MM-DD format. Defaults to today.")
    parser.add_argument("--database-path", type=Path, default=settings.database_path)
    parser.add_argument("--log-path", type=Path, default=settings.log_path)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file. Defaults to artifacts/chat-exports/<date>-chat-<chat-id>.txt",
    )
    args = parser.parse_args()

    day = _parse_day(args.date)
    output = args.output or settings.root / "artifacts" / "chat-exports" / f"{day.isoformat()}-chat-{args.chat_id}.txt"
    path = export_chat_records(
        chat_id=args.chat_id,
        day=day,
        paths=ExportPaths(
            database_path=args.database_path,
            log_path=args.log_path,
            output_path=output,
        ),
    )
    print(path)


if __name__ == "__main__":
    main()
