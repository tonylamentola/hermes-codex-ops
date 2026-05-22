from __future__ import annotations

from dataclasses import dataclass

from system.services.audit_log import AuditLog
from system.services.settings import settings


@dataclass
class TelegramNotifier:
    audit: AuditLog

    async def send(self, message: str, *, chat_ids: set[int] | None = None) -> int:
        chat_ids = chat_ids if chat_ids is not None else settings.allowed_chat_ids
        if not settings.telegram_bot_token:
            self.audit.write(
                agent="telegram-notifier",
                action="send",
                result="skipped",
                reason="missing TELEGRAM_BOT_TOKEN",
                message=message,
            )
            return 0
        if not chat_ids:
            self.audit.write(
                agent="telegram-notifier",
                action="send",
                result="skipped",
                reason="missing TELEGRAM_ALLOWED_CHAT_IDS",
                message=message,
            )
            return 0

        import httpx

        sent = 0
        async with httpx.AsyncClient(timeout=20) as client:
            for chat_id in chat_ids:
                response = await client.post(
                    f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                    json={"chat_id": chat_id, "text": message[:3900]},
                )
                response.raise_for_status()
                sent += 1
        self.audit.write(agent="telegram-notifier", action="send", result="ok", sent=sent)
        return sent


async def notify_telegram(message: str) -> int:
    return await TelegramNotifier(AuditLog()).send(message)
