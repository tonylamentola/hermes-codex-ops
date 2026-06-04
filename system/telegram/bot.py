from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
import html
from pathlib import Path
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from system.hermes.coordinator import HermesCoordinator
from system.hermes.openai_adapter import _backend as _build_ai_backend
from system.scripts.export_telegram_records import ExportPaths, export_chat_records
from system.telegram.conversation import chat_with_hermes
from system.services.audit_log import AuditLog
from system.services.control_state import ControlState
from system.services.memory import MemoryStore
from system.services.queue import TaskQueue
from system.services.queue import Task
from system.services.settings import settings
from system.services.worker import Worker, artifact_summary


audit = AuditLog()
queue = TaskQueue()
memory = MemoryStore()
hermes = HermesCoordinator.create(backend=_build_ai_backend())
control = ControlState.create()
APPROVE_WORDS = {"approve", "approved", "yes", "y", "run", "run it", "go", "go ahead", "do it"}
CANCEL_WORDS = {"cancel", "stop", "no", "never mind", "nevermind"}
TASK_QUERY_WORDS = {
    "task",
    "tasks",
    "what task",
    "what's the task",
    "whats the task",
    "what is the task",
    "what are the tasks",
    "what's pending",
    "whats pending",
    "pending",
    "queue",
}
HELP_WORDS = {"help", "commands", "what can you do"}
STATUS_WORDS = {"status", "system status", "queue status"}
CONTROL_SUMMARIES = APPROVE_WORDS | CANCEL_WORDS | TASK_QUERY_WORDS | HELP_WORDS | STATUS_WORDS


def _authorized(update: Update) -> bool:
    allowed = settings.allowed_chat_ids
    return not allowed or bool(update.effective_chat and update.effective_chat.id in allowed)


async def _guard(update: Update) -> bool:
    if _authorized(update):
        if update.effective_chat:
            audit.write(agent="telegram", action="authorized", result="ok", chat_id=update.effective_chat.id)
        return True
    audit.write(agent="telegram", action="unauthorized", result="blocked", chat_id=update.effective_chat.id if update.effective_chat else None)
    if update.message:
        await update.message.reply_text("Unauthorized chat.")
    return False


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    data = hermes.status()
    control_state = control.read()
    await update.message.reply_text(f"Queue: {data['queue']}\nPaused: {control_state.get('paused')} {control_state.get('reason', '')}")
    audit.write(agent="telegram", action="/status", result="ok")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    await update.message.reply_text(_help_text())
    audit.write(agent="telegram", action="/help", result="ok")


async def submit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    summary = " ".join(context.args).strip()
    if not summary:
        await update.message.reply_text("Usage: /submit TASK SUMMARY")
        return
    task = await hermes.submit_task(summary, priority=5, payload=_telegram_payload(update))
    await _reply_task_queued(update, task)
    audit.write(agent="telegram", action="/submit", result="queued", task_id=task.id)


async def plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    summary = " ".join(context.args).strip()
    if not summary:
        await update.message.reply_text("Usage: /plan TASK SUMMARY")
        return
    task = await hermes.submit_task(summary, priority=5, payload=_telegram_payload(update), decompose=True)
    subtasks = [
        item
        for item in queue.list(status="pending", limit=50)
        if item.payload.get("coordination", {}).get("root_task_id") == task.id
    ]
    lines = [f"Queued plan root: {task.id[:8]}"]
    for subtask in subtasks[:8]:
        lines.append(f"- {subtask.id[:8]} [{subtask.assigned_agent}] {subtask.summary}")
    await update.message.reply_text("\n".join(lines))
    audit.write(agent="telegram", action="/plan", result="queued", task_id=task.id, count=len(subtasks))


async def audit_capabilities(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    findings = hermes.audit_capabilities()
    lines = ["Hermes capability audit:"]
    for item in findings:
        lines.append(f"- {item['name']}: {item['status']}")
    await update.message.reply_text("\n".join(lines)[:3900])
    audit.write(agent="telegram", action="/audit_capabilities", result="ok")


def _telegram_payload(update: Update) -> dict[str, Any]:
    chat = update.effective_chat
    user = update.effective_user
    message = update.message
    return {
        "source": "telegram",
        "telegram": {
            "chat_id": chat.id if chat else None,
            "chat_type": chat.type if chat else None,
            "message_id": message.message_id if message else None,
            "message_text": message.text if message and message.text else None,
            "user_id": user.id if user else None,
            "username": user.username if user else None,
            "first_name": user.first_name if user else None,
        },
    }


def _task_ack(task_id: str) -> str:
    short_id = task_id[:8]
    return (
        f"Queued task: {short_id}\n\n"
        "Tap Approve when you want me to run it."
    )


def _task_keyboard(task_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Approve", callback_data=f"approve:{task_id}"),
                InlineKeyboardButton("Cancel", callback_data=f"cancel:{task_id}"),
            ],
            [InlineKeyboardButton("Details", callback_data=f"details:{task_id}")],
        ]
    )


async def _reply_task_queued(update: Update, task: Task) -> None:
    if update.message:
        await update.message.reply_text(_task_ack(task.id), reply_markup=_task_keyboard(task.id))


def _task_matches_chat(task: Task, chat_id: int) -> bool:
    telegram = task.payload.get("telegram")
    if not isinstance(telegram, dict):
        return False
    try:
        return int(telegram.get("chat_id")) == int(chat_id)
    except (TypeError, ValueError):
        return False


def _is_control_summary(summary: str) -> bool:
    return summary.strip().lower() in CONTROL_SUMMARIES


def _latest_chat_task(chat_id: int, *, include_control_tasks: bool = False) -> Task | None:
    for task in queue.list(limit=100):
        if not _task_matches_chat(task, chat_id):
            continue
        if task.status not in {"pending", "awaiting_approval", "active"}:
            continue
        if not include_control_tasks and _is_control_summary(task.summary):
            continue
        return task
    return None


def _chat_tasks(chat_id: int, *, limit: int = 6) -> list[Task]:
    tasks = []
    for task in queue.list(limit=200):
        if _task_matches_chat(task, chat_id) and not _is_control_summary(task.summary):
            tasks.append(task)
        if len(tasks) >= limit:
            break
    return tasks


def _tasks_overview(chat_id: int) -> str:
    tasks = _chat_tasks(chat_id)
    if not tasks:
        return "I do not see any real tasks from this chat yet. Send me the work you want done in one message."
    lines = ["Recent tasks:"]
    for task in tasks:
        lines.append(f"- {task.id[:8]} [{task.status}] {task.summary}")
    lines.append("\nReply approve to run the latest waiting task, or cancel to cancel it.")
    return "\n".join(lines)


def _help_text() -> str:
    return (
        "Send me a normal message to create a durable Hermes task.\n\n"
        "Natural controls:\n"
        "- approve / yes / go ahead: run the latest waiting task\n"
        "- cancel / stop: cancel the latest waiting task\n"
        "- status: queue status\n"
        "- tasks or what's the task: recent tasks\n\n"
        "Commands: /status, /tasks, /task TASK_ID, /approve TASK_ID, /cancel TASK_ID, "
        "/plan TASK SUMMARY, /audit_capabilities, /logs, /memory, /export_chat"
    )


def _approve_task(task_id: str, *, approved_by: str) -> Task:
    task = queue.get(task_id)
    if not task:
        raise KeyError(task_id)
    payload = dict(task.payload)
    payload["approved"] = True
    payload["approved_by"] = approved_by
    queue.update_payload(task.id, payload)
    approved = queue.update_status(task.id, "pending")
    memory.append_markdown("agent-status.md", "Task approved", f"- Task: `{approved.id}`\n- Summary: {approved.summary}")
    audit.write(agent="telegram", action="approve_task", result="queued", task_id=approved.id)
    return approved


def _approved_text(task: Task) -> str:
    return (
        f"Approved: {task.id[:8]}\n"
        f"Status: {task.status}\n\n"
        "I will wake the worker now and report back if it does not start."
    )


async def _wake_worker_after_approval(context: ContextTypes.DEFAULT_TYPE, task_id: str, chat_id: int | None) -> None:
    await asyncio.sleep(0.25)
    try:
        processed = await Worker.create().run_once()
        audit.write(
            agent="telegram",
            action="approval_worker_wake",
            result="processed" if processed else "idle",
            task_id=processed.id if processed else task_id,
        )
    except Exception as exc:  # noqa: BLE001
        audit.write(
            agent="telegram",
            action="approval_worker_wake",
            result="error",
            task_id=task_id,
            error=str(exc)[:500],
        )
        if chat_id is not None:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"Approved task {task_id[:8]}, but worker wake-up failed:\n{type(exc).__name__}: {str(exc)[:900]}",
            )
        return

    await asyncio.sleep(10)
    fresh = queue.get(task_id)
    if not fresh or chat_id is None:
        return
    if fresh.status in {"pending", "awaiting_approval"}:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"Task {fresh.id[:8]} is still {fresh.status} after approval.\n"
                "The background worker did not claim it yet. Use /status or /task "
                f"{fresh.id} for details."
            ),
        )
    elif fresh.status == "active":
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Task {fresh.id[:8]} is active now. I will send the result when the worker finishes.",
        )


def _schedule_worker_wake(context: ContextTypes.DEFAULT_TYPE, task: Task, chat_id: int | None) -> None:
    context.application.create_task(_wake_worker_after_approval(context, task.id, chat_id))


def _cancel_task(task_id: str) -> Task:
    task = queue.update_status(task_id, "cancelled")
    memory.append_markdown("agent-status.md", "Task cancelled", f"- Task: `{task.id}`\n- Summary: {task.summary}")
    audit.write(agent="telegram", action="cancel_task", result="cancelled", task_id=task.id)
    return task


def _details_text(task: Task) -> str:
    parts = [
        f"Task {task.id[:8]}",
        f"Status: {task.status}",
        f"Retries: {task.retry_count}",
        "",
        task.summary,
    ]
    if task.payload.get("backend"):
        parts.append(f"\nBackend: {task.payload['backend']}")
    parts.append("\n" + artifact_summary(task.payload.get("artifacts", [])))
    if task.payload.get("worker_result") or task.payload.get("worker_context"):
        result = str(task.payload.get("worker_result") or task.payload["worker_context"]).strip()
        parts.append("\nResult preview:\n" + result[:1200])
    return "\n".join(parts)


def _resolve_task(task_id: str) -> Task | None:
    exact = queue.get(task_id)
    if exact:
        return exact
    matches = [task for task in queue.list(limit=500) if task.id.startswith(task_id)]
    return matches[0] if len(matches) == 1 else None


async def _send_task_artifacts(update: Update, task: Task) -> None:
    if not update.message:
        return
    artifacts = task.payload.get("artifacts", [])
    existing = [artifact for artifact in artifacts if artifact.get("exists")]
    if not artifacts:
        await update.message.reply_text("No artifacts were reported for this task.")
        return
    if not existing:
        await update.message.reply_text(artifact_summary(artifacts))
        return
    sent = 0
    for artifact in existing[:5]:
        path = Path(str(artifact["path"]))
        if not path.exists():
            continue
        caption = f"{task.id[:8]}: {artifact.get('display_path', path.name)}"
        with path.open("rb") as handle:
            if artifact.get("kind") == "image":
                await update.message.reply_photo(photo=handle, caption=caption[:1024])
            else:
                await update.message.reply_document(document=handle, caption=caption[:1024])
        sent += 1
    if sent == 0:
        await update.message.reply_text(artifact_summary(artifacts))


async def plain_text_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    if not update.message or not update.message.text:
        return
    summary = update.message.text.strip()
    if not summary:
        return
    normalized = summary.lower()
    if normalized in HELP_WORDS:
        await update.message.reply_text(_help_text())
        audit.write(agent="telegram", action="plain_text_help", result="ok")
        return
    if normalized in STATUS_WORDS:
        data = hermes.status()
        control_state = control.read()
        await update.message.reply_text(
            f"Queue: {data['queue']}\nPaused: {control_state.get('paused')} {control_state.get('reason', '')}"
        )
        audit.write(agent="telegram", action="plain_text_status", result="ok")
        return
    if normalized in TASK_QUERY_WORDS:
        await update.message.reply_text(_tasks_overview(update.effective_chat.id))
        audit.write(agent="telegram", action="plain_text_tasks", result="ok")
        return
    if normalized in APPROVE_WORDS or normalized in CANCEL_WORDS:
        task = _latest_chat_task(update.effective_chat.id)
        if not task:
            await update.message.reply_text("I do not see a recent task in this chat to act on.")
            return
        if normalized in APPROVE_WORDS:
            approved = _approve_task(task.id, approved_by="telegram-text")
            await update.message.reply_text(_approved_text(approved))
            _schedule_worker_wake(context, approved, update.effective_chat.id if update.effective_chat else None)
            return
        cancelled = _cancel_task(task.id)
        await update.message.reply_text(f"Cancelled: {cancelled.id[:8]}")
        return
    chat_id = update.effective_chat.id if update.effective_chat else None
    explicit_task = False
    for prefix in ("task:", "queue:", "todo:"):
        if normalized.startswith(prefix):
            summary = summary.split(":", 1)[1].strip()
            explicit_task = True
            break

    if explicit_task:
        if not summary:
            await update.message.reply_text(
                "Give me something after `task:` -- e.g. `task: deploy the staging build`."
            )
            audit.write(agent="telegram", action="plain_text_task", result="empty_prefix")
            return
        task = await hermes.submit_task(
            summary, priority=5, payload=_telegram_payload(update)
        )
        memory.append_markdown(
            "active-projects.md",
            "Telegram task submitted",
            f"- Task: `{task.id}`\n- Summary: {summary}\n- Chat: `{chat_id if chat_id is not None else 'unknown'}`",
        )
        await _reply_task_queued(update, task)
        audit.write(
            agent="telegram", action="plain_text_task", result="queued", task_id=task.id
        )
        return

    # Conversational fallback -- route through the Hermes AI backend.
    try:
        reply, queue_summary = await chat_with_hermes(
            hermes,
            user_text=summary,
            chat_id=chat_id,
            audit=audit,
            memory=memory,
            queue=queue,
        )
    except Exception as exc:  # noqa: BLE001
        audit.write(
            agent="telegram",
            action="conversation",
            result="error",
            error=str(exc)[:500],
            chat_id=chat_id,
        )
        await update.message.reply_text(
            "Hermes hit a backend error trying to reply. Try again in a moment, "
            "or say `task: <thing>` to force a durable task.\n\nError: "
            f"{type(exc).__name__}: {str(exc)[:300]}"
        )
        return

    if queue_summary:
        task = await hermes.submit_task(
            queue_summary, priority=5, payload=_telegram_payload(update)
        )
        memory.append_markdown(
            "active-projects.md",
            "Telegram task submitted (via conversation)",
            f"- Task: `{task.id}`\n- Summary: {queue_summary}\n- Chat: `{chat_id if chat_id is not None else 'unknown'}`",
        )
        reply = (
            (reply + "\n\n" if reply else "")
            + f"(Queued task {task.id[:8]}: {queue_summary})"
        )
        audit.write(
            agent="telegram",
            action="conversation",
            result="queued",
            task_id=task.id,
            chat_id=chat_id,
        )
        await _reply_task_queued(update, task)
    else:
        audit.write(
            agent="telegram", action="conversation", result="ok", chat_id=chat_id
        )
        await update.message.reply_text(reply[:4000])


async def task_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    if not await _guard(update):
        await query.answer("Unauthorized")
        return
    action, _, task_id = (query.data or "").partition(":")
    task = queue.get(task_id)
    if not task:
        await query.answer("Unknown task")
        await query.edit_message_text("I could not find that task anymore.")
        return
    if update.effective_chat and not _task_matches_chat(task, update.effective_chat.id):
        await query.answer("Wrong chat")
        return
    if action == "approve":
        approved = _approve_task(task.id, approved_by="telegram-button")
        await query.answer("Approved")
        await query.edit_message_text(f"{_approved_text(approved)}\n\n{approved.summary}")
        _schedule_worker_wake(context, approved, update.effective_chat.id if update.effective_chat else None)
    elif action == "cancel":
        cancelled = _cancel_task(task.id)
        await query.answer("Cancelled")
        await query.edit_message_text(f"Cancelled: {cancelled.id[:8]}\n{cancelled.summary}")
    elif action == "details":
        await query.answer("Details")
        await query.edit_message_text(_details_text(task), reply_markup=_task_keyboard(task.id))


async def tasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    lines = [f"{task.status} p{task.priority} r{task.retry_count} {task.id[:8]} - {task.summary}" for task in queue.list(limit=20)]
    await update.message.reply_text("\n".join(lines) or "No tasks.")
    audit.write(agent="telegram", action="/tasks", result="ok")


async def task_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: /task TASK_ID")
        return
    task = _resolve_task(context.args[0])
    if not task:
        await update.message.reply_text(f"Unknown or ambiguous task: {context.args[0]}")
        return
    await update.message.reply_text(_details_text(task)[:3900])
    audit.write(agent="telegram", action="/task", result="ok", task_id=task.id)


async def artifacts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: /artifacts TASK_ID")
        return
    task = _resolve_task(context.args[0])
    if not task:
        await update.message.reply_text(f"Unknown or ambiguous task: {context.args[0]}")
        return
    await _send_task_artifacts(update, task)
    audit.write(agent="telegram", action="/artifacts", result="ok", task_id=task.id)


async def stalled(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    lines = [f"{task.id[:8]} - {task.summary}" for task in queue.list(status="stalled", limit=20)]
    await update.message.reply_text("\n".join(lines) or "No stalled tasks.")
    audit.write(agent="telegram", action="/stalled", result="ok")


async def logs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    lines = [f"{row['timestamp']} {row['agent']} {row['action']} {row['result']}" for row in audit.tail(10)]
    await update.message.reply_text("\n".join(lines) or "No logs.")
    audit.write(agent="telegram", action="/logs", result="ok")


async def memory_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    text = memory.read_markdown("active-projects.md", max_chars=2000)
    await update.message.reply_text(html.escape(text) or "No memory yet.")
    audit.write(agent="telegram", action="/memory", result="ok")


def _parse_export_date(raw: str | None) -> date:
    if not raw:
        return datetime.now(UTC).date()
    return date.fromisoformat(raw)


async def export_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    if not update.effective_chat or not update.message:
        return
    try:
        day = _parse_export_date(context.args[0] if context.args else None)
    except ValueError:
        await update.message.reply_text("Usage: /export_chat optional-YYYY-MM-DD")
        return

    chat_id = int(update.effective_chat.id)
    output = settings.root / "artifacts" / "chat-exports" / f"{day.isoformat()}-chat-{chat_id}.txt"
    path = export_chat_records(
        chat_id=chat_id,
        day=day,
        paths=ExportPaths(
            database_path=settings.database_path,
            log_path=settings.log_path,
            output_path=output,
        ),
    )
    audit.write(
        agent="telegram",
        action="/export_chat",
        result="created",
        chat_id=chat_id,
        path=str(path),
    )
    with path.open("rb") as handle:
        await update.message.reply_document(
            document=handle,
            filename=path.name,
            caption=(
                "Durable Hermes chat export. Raw Telegram message bodies are only included "
                "if they were explicitly persisted in durable task/log state."
            ),
        )
    audit.write(
        agent="telegram",
        action="/export_chat",
        result="sent",
        chat_id=chat_id,
        path=str(path),
    )


async def retry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: /retry TASK_ID")
        return
    task = queue.update_status(context.args[0], "pending", retry_increment=True)
    audit.write(agent="telegram", action="/retry", result="queued", task_id=task.id)
    await update.message.reply_text(f"Queued retry: {task.id}")


async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    reason = " ".join(context.args).strip()
    state = control.pause(reason=reason, updated_by="telegram")
    memory.append_markdown("agent-status.md", "Operator paused worker", f"Reason: {reason or 'No reason provided.'}")
    await update.message.reply_text(f"Worker paused: {state['reason'] or 'no reason'}")
    audit.write(agent="telegram", action="/pause", result="ok")


async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    control.resume(updated_by="telegram")
    memory.append_markdown("agent-status.md", "Operator resumed worker", "Worker processing resumed.")
    await update.message.reply_text("Worker resumed.")
    audit.write(agent="telegram", action="/resume", result="ok")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: /cancel TASK_ID")
        return
    task = _cancel_task(context.args[0])
    await update.message.reply_text(f"Cancelled task: {task.id}")


async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: /approve TASK_ID")
        return
    task_id = context.args[0]
    task = queue.get(task_id)
    if not task:
        await update.message.reply_text(f"Unknown task: {task_id}")
        return
    approved = _approve_task(task.id, approved_by="telegram-command")
    await update.message.reply_text(_approved_text(approved))
    _schedule_worker_wake(context, approved, update.effective_chat.id if update.effective_chat else None)


async def projects(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    await update.message.reply_text(memory.read_markdown("active-projects.md", 2000) or "No projects.")
    audit.write(agent="telegram", action="/projects", result="ok")


async def deployments(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    await update.message.reply_text(memory.read_markdown("deployment-history.md", 2000) or "No deployments.")
    audit.write(agent="telegram", action="/deployments", result="ok")


async def agents(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    await update.message.reply_text(memory.read_markdown("agent-status.md", 2000) or "No agent state.")
    audit.write(agent="telegram", action="/agents", result="ok")


def build_app() -> Application:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")
    memory.ensure_baseline()
    app = Application.builder().token(settings.telegram_bot_token).build()
    for name, handler in {
        "status": status,
        "start": help_cmd,
        "help": help_cmd,
        "submit": submit,
        "plan": plan,
        "audit_capabilities": audit_capabilities,
        "projects": projects,
        "deployments": deployments,
        "tasks": tasks,
        "task": task_details,
        "artifacts": artifacts,
        "stalled": stalled,
        "logs": logs,
        "export_chat": export_chat,
        "retry": retry,
        "pause": pause,
        "resume": resume,
        "cancel": cancel,
        "approve": approve,
        "memory": memory_cmd,
        "agents": agents,
    }.items():
        app.add_handler(CommandHandler(name, handler))
    app.add_handler(CallbackQueryHandler(task_button, pattern="^(approve|cancel|details):"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, plain_text_task))
    return app


def main() -> None:
    audit.write(agent="telegram", action="start", result="starting")
    build_app().run_polling()


if __name__ == "__main__":
    main()
