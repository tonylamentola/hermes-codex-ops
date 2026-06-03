from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from system.services.audit_log import utc_now
from system.services.settings import settings


TASK_STATUSES = {"pending", "planned", "active", "stalled", "completed", "failed", "cancelled", "awaiting_approval"}


@dataclass
class Task:
    id: str
    timestamp: str
    assigned_agent: str
    priority: int
    retry_count: int
    status: str
    summary: str
    payload: dict[str, Any]
    updated_at: str


class TaskQueue:
    def __init__(self, database_path: Path | None = None, tasks_dir: Path | None = None) -> None:
        self.database_path = database_path or settings.database_path
        self.tasks_dir = tasks_dir or settings.root / "tasks"
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    assigned_agent TEXT NOT NULL,
                    priority INTEGER NOT NULL,
                    retry_count INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority DESC)")

    def create(
        self,
        *,
        summary: str,
        assigned_agent: str = "hermes",
        priority: int = 5,
        payload: dict[str, Any] | None = None,
    ) -> Task:
        now = utc_now()
        task = Task(
            id=str(uuid.uuid4()),
            timestamp=now,
            assigned_agent=assigned_agent,
            priority=priority,
            retry_count=0,
            status="pending",
            summary=summary,
            payload=payload or {},
            updated_at=now,
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO tasks
                (id, timestamp, assigned_agent, priority, retry_count, status, summary, payload, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.id,
                    task.timestamp,
                    task.assigned_agent,
                    task.priority,
                    task.retry_count,
                    task.status,
                    task.summary,
                    json.dumps(task.payload, sort_keys=True),
                    task.updated_at,
                ),
            )
        self.export_json()
        return task

    def update_status(self, task_id: str, status: str, *, retry_increment: bool = False) -> Task:
        if status not in TASK_STATUSES:
            raise ValueError(f"Unsupported task status: {status}")
        now = utc_now()
        with self._connect() as conn:
            if retry_increment:
                conn.execute(
                    "UPDATE tasks SET status = ?, retry_count = retry_count + 1, updated_at = ? WHERE id = ?",
                    (status, now, task_id),
                )
            else:
                conn.execute(
                    "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
                    (status, now, task_id),
                )
        task = self.get(task_id)
        if not task:
            raise KeyError(task_id)
        self.export_json()
        return task

    def update_payload(self, task_id: str, payload: dict[str, Any]) -> Task:
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE tasks SET payload = ?, updated_at = ? WHERE id = ?",
                (json.dumps(payload, sort_keys=True), now, task_id),
            )
        task = self.get(task_id)
        if not task:
            raise KeyError(task_id)
        self.export_json()
        return task

    def claim_next(self, *, assigned_agent: str = "codex") -> Task | None:
        now = utc_now()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT * FROM tasks
                WHERE status = 'pending' AND assigned_agent = ?
                ORDER BY priority DESC, timestamp ASC
                LIMIT 1
                """,
                (assigned_agent,),
            ).fetchone()
            if not row:
                conn.commit()
                return None
            conn.execute(
                "UPDATE tasks SET status = 'active', updated_at = ? WHERE id = ?",
                (now, row["id"]),
            )
            conn.commit()
        task = self.get(row["id"])
        self.export_json()
        return task

    def get(self, task_id: str) -> Task | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return self._row_to_task(row) if row else None

    def list(self, status: str | None = None, limit: int = 50) -> list[Task]:
        with self._connect() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM tasks WHERE status = ? ORDER BY priority DESC, timestamp ASC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM tasks ORDER BY updated_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [self._row_to_task(row) for row in rows]

    def export_json(self) -> None:
        for status in ("active", "pending", "planned", "stalled", "completed", "failed", "cancelled", "awaiting_approval"):
            tasks = [asdict(task) for task in self.list(status=status, limit=200)]
            (self.tasks_dir / f"{status}.json").write_text(
                json.dumps(tasks, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

    @staticmethod
    def _row_to_task(row: sqlite3.Row) -> Task:
        return Task(
            id=row["id"],
            timestamp=row["timestamp"],
            assigned_agent=row["assigned_agent"],
            priority=row["priority"],
            retry_count=row["retry_count"],
            status=row["status"],
            summary=row["summary"],
            payload=json.loads(row["payload"]),
            updated_at=row["updated_at"],
        )
