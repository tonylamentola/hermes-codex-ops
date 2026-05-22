from __future__ import annotations

import html
from typing import Any

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from system.hermes.coordinator import HermesCoordinator
from system.services.audit_log import AuditLog
from system.services.control_state import ControlState
from system.services.memory import MemoryStore
from system.services.queue import TaskQueue
from system.services.settings import settings


audit = AuditLog()
queue = TaskQueue()
memory = MemoryStore()
hermes = HermesCoordinator.create()
control = ControlState.create()


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
    task = await hermes.submit_task(summary, priority=5, payload={"source": "telegram"})
    await update.message.reply_text(f"Queued task: {task.id}")
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
        f"Queued task: {short_id}\n"
        "I will update you here when it starts, completes, fails, or needs approval.\n"
        f"Use /tasks to see the queue or /cancel {task_id} to cancel it."
    )


async def plain_text_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update):
        return
    if not update.message or not update.message.text:
        return
    summary = update.message.text.strip()
    if not summary:
        return
    task = await hermes.submit_task(summary, priority=5, payload=_telegram_payload(update))
    memory.append_markdown(
        "active-projects.md",
        "Telegram task submitted",
        f"- Task: `{task.id}`\n- Summary: {summary}\n- Chat: `{update.effective_chat.id if update.effective_chat else 'unknown'}`",
    )
    await update.message.reply_text(_task_ack(task.id))
    audit.write(agent="telegram", action="plain_text_task", result="queued", task_id=task.id)


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
    task = queue.update_status(context.args[0], "cancelled")
    memory.append_markdown("agent-status.md", "Task cancelled", f"- Task: `{task.id}`\n- Summary: {task.summary}")
    await update.message.reply_text(f"Cancelled task: {task.id}")
    audit.write(agent="telegram", action="/cancel", result="cancelled", task_id=task.id)


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
    payload = dict(task.payload)
    payload["approved"] = True
    payload["approved_by"] = "telegram"
    queue.update_payload(task.id, payload)
    approved = queue.update_status(task.id, "pending")
    memory.append_markdown("agent-status.md", "Task approved", f"- Task: `{approved.id}`\n- Summary: {approved.summary}")
    await update.message.reply_text(f"Approved task: {approved.id}")
    audit.write(agent="telegram", action="/approve", result="queued", task_id=approved.id)


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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, plain_text_task))
    return app


def main() -> None:
    audit.write(agent="telegram", action="start", result="starting")
    build_app().run_polling()


if __name__ == "__main__":
    main()
