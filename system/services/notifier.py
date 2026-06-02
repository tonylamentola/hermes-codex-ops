from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import shutil
import subprocess

from system.services.audit_log import AuditLog
from system.services.settings import settings

PHOTO_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def _svg_preview_path(file_path: Path) -> Path:
    digest = hashlib.sha256(str(file_path).encode("utf-8")).hexdigest()[:12]
    output_dir = settings.root / "artifacts" / "telegram-previews"
    return output_dir / f"{file_path.stem}-{digest}.png"


def telegram_upload_path(file_path: Path) -> tuple[Path, str, str]:
    """Return the path, endpoint, and multipart field to use for Telegram."""
    suffix = file_path.suffix.lower()
    if suffix in PHOTO_EXTENSIONS:
        return file_path, "sendPhoto", "photo"
    if suffix == ".svg":
        converter = shutil.which("rsvg-convert")
        if converter:
            output = _svg_preview_path(file_path)
            if not output.exists() or output.stat().st_mtime < file_path.stat().st_mtime:
                output.parent.mkdir(parents=True, exist_ok=True)
                subprocess.run(
                    [converter, "-f", "png", "-o", str(output), str(file_path)],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            if output.exists():
                return output, "sendPhoto", "photo"
    return file_path, "sendDocument", "document"


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

    async def send_file(self, path: str, *, caption: str = "", chat_ids: set[int] | None = None) -> int:
        chat_ids = chat_ids if chat_ids is not None else settings.allowed_chat_ids
        file_path = Path(path)
        if not settings.telegram_bot_token or not chat_ids or not file_path.exists():
            self.audit.write(
                agent="telegram-notifier",
                action="send_file",
                result="skipped",
                path=str(file_path),
                reason="missing token/chat ids/file",
            )
            return 0

        import httpx

        try:
            upload_path, endpoint, field = telegram_upload_path(file_path)
        except (OSError, subprocess.CalledProcessError) as exc:
            self.audit.write(
                agent="telegram-notifier",
                action="convert_svg",
                result="failed",
                path=str(file_path),
                error=str(exc),
            )
            upload_path, endpoint, field = file_path, "sendDocument", "document"
        sent = 0
        async with httpx.AsyncClient(timeout=60) as client:
            for chat_id in chat_ids:
                with upload_path.open("rb") as handle:
                    response = await client.post(
                        f"https://api.telegram.org/bot{settings.telegram_bot_token}/{endpoint}",
                        data={"chat_id": chat_id, "caption": caption[:1024]},
                        files={field: (upload_path.name, handle)},
                    )
                response.raise_for_status()
                sent += 1
        self.audit.write(
            agent="telegram-notifier",
            action="send_file",
            result="ok",
            sent=sent,
            path=str(file_path),
            upload_path=str(upload_path),
            endpoint=endpoint,
        )
        return sent


async def notify_telegram(message: str) -> int:
    return await TelegramNotifier(AuditLog()).send(message)
