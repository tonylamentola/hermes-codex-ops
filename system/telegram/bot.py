from __future__ import annotations

import html
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from system.hermes.coordinator import HermesCoordinator
from system.services.audit_log import AuditLog
from system.services.control_state import ControlState
from system.services.memory import MemoryStore
from system.services.queue import TaskQueue
from system.services.queue import Task
from system.services.settings import settings


audit = AuditLog()
queue = TaskQueue()
memory = MemoryStore()
hermes = HermesCoordinator.create()
control = ControlState.create()
APPROVE_WORDS = {"approve", "approved", "yes", "y", "run", "run it", "go", "go ahead", "do it"}
CANCEL_WORDS = {"cancel", "stop", "no", "never mind", "nevermind"}


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


def _latest_chat_task(chat_id: int) -> Task | None:
    for task in queue.list(limit=100):
        if _task_matches_chat(task, chat_id) and task.status in {"pending", "awaiting_approval", "active"}:
            return task
    return None


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


def _cancel_task(task_id: str) -> Task:
    task = queue.update_status(task_id, "cancelled")
    memory.append_markdown("agent-status.md", "Task cancelled", f"- Task: `{task.id}`\n- Summary: {task.summary}")
    audit.write(agent="telegram", action="cancel_task", result="cancelled", task_id=task.id)
    return task


def _details_text(task: Task) -> str:
    return f"Task {task.id[:8]}\nStatus: {task.status}\n\n{task.summary}"


async def plain_text_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    if not update.message or not update.message.text:
        return
    summary = update.message.text.strip()
    if not summary:
        return
    normalized = summary.lower()
    if normalized in APPROVE_WORDS or normalized in CANCEL_WORDS:
        task = _latest_chat_task(update.effective_chat.id)
        if not task:
            await update.message.reply_text("I do not see a recent task in this chat to act on.")
            return
        if normalized in APPROVE_WORDS:
            approved = _approve_task(task.id, approved_by="telegram-text")
            await update.message.reply_text(f"Approved: {approved.id[:8]}\nI will start it from the queue.")
            return
        cancelled = _cancel_task(task.id)
        await update.message.reply_text(f"Cancelled: {cancelled.id[:8]}")
        return
    task = await hermes.submit_task(summary, priority=5, payload=_telegram_payload(update))
    memory.append_markdown(
        "active-projects.md",
        "Telegram task submitted",
        f"- Task: `{task.id}`\n- Summary: {summary}\n- Chat: `{update.effective_chat.id if update.effective_chat else 'unknown'}`",
    )
    await _reply_task_queued(update, task)
    audit.write(agent="telegram", action="plain_text_task", result="queued", task_id=task.id)


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
        await query.edit_message_text(f"Approved: {approved.id[:8]}\n{approved.summary}")
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
    await update.message.reply_text(f"Approved task: {approved.id}")


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
        "submit": submit,
        "projects": projects,
        "deployments": deployments,
        "tasks": tasks,
        "stalled": stalled,
        "logs": logs,
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
