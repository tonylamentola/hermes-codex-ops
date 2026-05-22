from __future__ import annotations

import asyncio


async def notify_telegram_async(message: str) -> None:
    from system.services.notifier import notify_telegram as send_notification

    await send_notification(message)


def notify_telegram(message: str) -> None:
    asyncio.run(notify_telegram_async(message))
