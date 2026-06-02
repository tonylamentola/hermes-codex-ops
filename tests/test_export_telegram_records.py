from __future__ import annotations

import json
import sqlite3
from datetime import date

from system.scripts.export_telegram_records import ExportPaths, export_chat_records


def _init_queue(path):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE tasks (
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


def _insert_task(path, *, task_id, timestamp, chat_id, status="completed", summary="Do work"):
    payload = {
        "telegram": {"chat_id": chat_id},
        "worker_context": "Finished the work and wrote durable state.",
    }
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO tasks
            (id, timestamp, assigned_agent, priority, retry_count, status, summary, payload, updated_at)
            VALUES (?, ?, 'codex', 5, 0, ?, ?, ?, ?)
            """,
            (task_id, timestamp, status, summary, json.dumps(payload), timestamp),
        )


def test_export_chat_records_includes_matching_tasks_and_events(tmp_path):
    database_path = tmp_path / "queue.sqlite3"
    log_path = tmp_path / "ops.jsonl"
    output_path = tmp_path / "chat.txt"
    _init_queue(database_path)
    _insert_task(
        database_path,
        task_id="task-1",
        timestamp="2026-06-01T12:00:00+00:00",
        chat_id=7272977804,
        summary="Build Hermes into an ultimate agent",
    )
    _insert_task(
        database_path,
        task_id="task-2",
        timestamp="2026-06-01T12:05:00+00:00",
        chat_id=111,
        summary="Wrong chat",
    )
    log_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2026-06-01T12:00:01+00:00",
                        "agent": "telegram",
                        "action": "conversation",
                        "result": "queued",
                        "chat_id": 7272977804,
                        "task_id": "task-1",
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-06-01T12:05:01+00:00",
                        "agent": "telegram",
                        "action": "conversation",
                        "result": "queued",
                        "chat_id": 111,
                        "task_id": "task-2",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    export_chat_records(
        chat_id=7272977804,
        day=date(2026, 6, 1),
        paths=ExportPaths(database_path=database_path, log_path=log_path, output_path=output_path),
    )

    text = output_path.read_text(encoding="utf-8")
    assert "Raw Telegram message bodies are not persisted" in text
    assert "Build Hermes into an ultimate agent" in text
    assert "telegram.conversation" in text
    assert "Finished the work" in text
    assert "Wrong chat" not in text


def test_export_chat_records_handles_missing_sources(tmp_path):
    output_path = tmp_path / "chat.txt"

    export_chat_records(
        chat_id=7272977804,
        day=date(2026, 6, 1),
        paths=ExportPaths(
            database_path=tmp_path / "missing.sqlite3",
            log_path=tmp_path / "missing.jsonl",
            output_path=output_path,
        ),
    )

    text = output_path.read_text(encoding="utf-8")
    assert "Today's Chat-Linked Tasks:\n- none" in text
    assert "Event Timeline (UTC):\n- none" in text
