from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - lets operator scripts run before pip install
    def load_dotenv() -> None:
        return None


load_dotenv()


def _default_root() -> Path:
    return Path(os.getenv("OPS_ROOT", Path(__file__).resolve().parents[2])).resolve()


@dataclass(frozen=True)
class Settings:
    root: Path = _default_root()
    database_path: Path = Path(os.getenv("DATABASE_PATH", _default_root() / "tasks" / "queue.sqlite3"))
    log_path: Path = Path(os.getenv("LOG_PATH", _default_root() / "logs" / "ops.jsonl"))
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_codex_model: str = os.getenv("OPENAI_CODEX_MODEL", "gpt-5.3-codex")
    worker_backend: str = os.getenv("WORKER_BACKEND", "dry-run")
    worker_poll_seconds: int = int(os.getenv("WORKER_POLL_SECONDS", "15"))
    worker_max_retries: int = int(os.getenv("WORKER_MAX_RETRIES", "3"))
    worker_require_approval: bool = os.getenv("WORKER_REQUIRE_APPROVAL", "false").lower() == "true"
    codex_cli_model: str = os.getenv("CODEX_CLI_MODEL", "gpt-5.3-codex")
    codex_cli_sandbox: str = os.getenv("CODEX_CLI_SANDBOX", "read-only")
    codex_cli_timeout_seconds: int = int(os.getenv("CODEX_CLI_TIMEOUT_SECONDS", "600"))
    memory_compression_backend: str = os.getenv("MEMORY_COMPRESSION_BACKEND", "dry-run")
    memory_context_max_chars: int = int(os.getenv("MEMORY_CONTEXT_MAX_CHARS", "12000"))
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_allowed_chat_ids: str = os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "")
    github_token: str = os.getenv("GITHUB_TOKEN", "")
    github_owner: str = os.getenv("GITHUB_OWNER", "")
    hermes_api_key: str = os.getenv("HERMES_API_KEY", "")
    dashboard_webhook_secret: str = os.getenv("HERMES_DASHBOARD_SECRET", "")
    codex_jobs_path: str = os.getenv(
        "CODEX_JOBS_PATH", "/Users/anthonylamentola/cued/telegram-codex-bridge/jobs.json"
    )

    @property
    def allowed_chat_ids(self) -> set[int]:
        if not self.telegram_allowed_chat_ids.strip():
            return set()
        return {int(item.strip()) for item in self.telegram_allowed_chat_ids.split(",") if item.strip()}


settings = Settings()
