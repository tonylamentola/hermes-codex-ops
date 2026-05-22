from __future__ import annotations

from typing import Protocol
from dataclasses import dataclass
import asyncio
import shutil

from system.services.settings import settings


class AIBackend(Protocol):
    name: str

    async def complete(self, prompt: str, *, system: str = "") -> str:
        """Return a text completion from the backend."""


@dataclass
class CodexBackend:
    name: str = "codex-api"

    async def complete(self, prompt: str, *, system: str = "") -> str:
        import httpx

        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for CodexBackend")
        headers = {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": settings.openai_codex_model,
            "input": [
                {"role": "system", "content": system or "You are Codex, a precise coding agent."},
                {"role": "user", "content": prompt},
            ],
        }
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post("https://api.openai.com/v1/responses", headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        return data.get("output_text", "")


@dataclass
class DryRunBackend:
    name: str = "dry-run"

    async def complete(self, prompt: str, *, system: str = "") -> str:
        return f"DRY RUN BACKEND\nSystem: {system[:200]}\nPrompt: {prompt[:1000]}"


@dataclass
class CodexCliBackend:
    name: str = "codex-cli"

    async def complete(self, prompt: str, *, system: str = "") -> str:
        if not shutil.which("codex"):
            raise RuntimeError("codex CLI is not installed or not on PATH")
        full_prompt = f"{system.strip()}\n\n{prompt.strip()}".strip()
        command = [
            "codex",
            "exec",
            "--skip-git-repo-check",
            "--sandbox",
            settings.codex_cli_sandbox,
            "--ask-for-approval",
            "never",
            "--model",
            settings.codex_cli_model,
            "-",
        ]
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate(full_prompt.encode("utf-8"))
        if proc.returncode != 0:
            raise RuntimeError(stderr.decode("utf-8", errors="replace")[-2000:])
        return stdout.decode("utf-8", errors="replace").strip()
