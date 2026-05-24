"""Conversational layer for the Hermes Telegram bot.

Routes natural-language messages through the configured Hermes AI backend
(codex-cli per WORKER_BACKEND) using HERMES_SYSTEM_PROMPT plus a Telegram
persona overlay loaded from config/telegram_persona.md. The model can
request a durable task by including a marker like:

    [[QUEUE: short summary]]

in its reply; the caller will strip the marker, submit the task, and
append a tiny acknowledgement line.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from system.hermes.coordinator import HERMES_SYSTEM_PROMPT, HermesCoordinator
from system.services.audit_log import AuditLog
from system.services.memory import MemoryStore
from system.services.queue import TaskQueue

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PERSONA_PATH = _PROJECT_ROOT / "config" / "telegram_persona.md"
_HANDOFFS_NAME = "summaries/handoffs.md"
_CONTEXT_PACK_NAME = "summaries/context-pack.md"
_ACTIVE_PROJECTS_NAME = "active-projects.md"

_QUEUE_RE = re.compile(r"\[\[\s*QUEUE\s*:\s*(.+?)\s*\]\]", re.IGNORECASE | re.DOTALL)


def _load_persona() -> str:
    try:
        return _PERSONA_PATH.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return (
            "You are Hermes on Telegram. Reply briefly and conversationally in "
            "plain English. Never emit JSON or worker instructions unless the "
            "operator explicitly asks for them."
        )


def _recent_tasks_block(queue: TaskQueue, chat_id: int | None, limit: int = 6) -> str:
    if chat_id is None:
        return "(no chat id)"
    rows: list[str] = []
    for task in queue.list(limit=200):
        payload = getattr(task, "payload", None) or {}
        task_chat = None
        if isinstance(payload, dict):
            telegram = payload.get("telegram") or {}
            if isinstance(telegram, dict):
                task_chat = telegram.get("chat_id")
        if task_chat is None or task_chat != chat_id:
            continue
        rows.append(f"- {task.id[:8]} [{task.status}] {task.summary}")
        if len(rows) >= limit:
            break
    return "\n".join(rows) if rows else "(no recent tasks for this chat)"


def _audit_tail(audit: AuditLog, limit: int = 8) -> str:
    try:
        entries = audit.tail(limit)
    except Exception:
        return ""
    lines: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            lines.append(str(entry))
            continue
        lines.append(
            "- "
            + " ".join(
                f"{k}={v}" for k, v in entry.items()
                if k in {"ts", "agent", "action", "result", "task_id"}
            )
        )
    return "\n".join(lines)


def _memory_snippet(memory: MemoryStore, name: str, max_chars: int = 1500) -> str:
    try:
        text = memory.read_markdown(name, max_chars=max_chars)
    except Exception:
        return ""
    return text or ""


def _build_system_prompt() -> str:
    persona = _load_persona()
    return f"{persona}\n\n---\n\n{HERMES_SYSTEM_PROMPT}"


def _build_user_prompt(
    user_text: str,
    *,
    chat_id: int | None,
    queue: TaskQueue,
    memory: MemoryStore,
    audit: AuditLog,
) -> str:
    parts = [
        f"Operator message (chat_id={chat_id}):",
        user_text.strip(),
        "",
        "--- Recent tasks for this chat ---",
        _recent_tasks_block(queue, chat_id),
        "",
        "--- Recent audit log ---",
        _audit_tail(audit) or "(empty)",
    ]
    handoffs = _memory_snippet(memory, _HANDOFFS_NAME, max_chars=1200)
    if handoffs:
        parts.extend(["", "--- Latest handoffs notes ---", handoffs])
    context_pack = _memory_snippet(memory, _CONTEXT_PACK_NAME, max_chars=1800)
    if context_pack:
        parts.extend(["", "--- Context pack ---", context_pack])
    active = _memory_snippet(memory, _ACTIVE_PROJECTS_NAME, max_chars=1200)
    if active:
        parts.extend(["", "--- Active projects ---", active])
    parts.extend([
        "",
        "Reply to the operator conversationally now.",
    ])
    return "\n".join(parts)


async def chat_with_hermes(
    hermes: HermesCoordinator,
    *,
    user_text: str,
    chat_id: int | None,
    audit: AuditLog,
    memory: MemoryStore,
    queue: TaskQueue,
) -> tuple[str, str | None]:
    """Return (reply_text, queue_summary_or_None).

    The caller is responsible for: actually calling hermes.submit_task when
    queue_summary is not None, appending a memory entry only in that case,
    and sending reply_text to Telegram.
    """
    system = _build_system_prompt()
    prompt = _build_user_prompt(
        user_text,
        chat_id=chat_id,
        queue=queue,
        memory=memory,
        audit=audit,
    )
    raw = await hermes.backend.complete(prompt, system=system)
    if not raw:
        return (
            "(Hermes returned an empty reply -- try rephrasing, or say "
            "`task: <thing>` to force a durable task.)",
            None,
        )
    queue_summary: str | None = None
    match = _QUEUE_RE.search(raw)
    if match:
        queue_summary = match.group(1).strip() or None
        raw = _QUEUE_RE.sub("", raw).strip()
    return raw.strip() or "(no reply)", queue_summary
