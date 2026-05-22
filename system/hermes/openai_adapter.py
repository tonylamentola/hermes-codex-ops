from __future__ import annotations

import time
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from system.hermes.coordinator import HERMES_SYSTEM_PROMPT, HermesCoordinator
from system.services.ai_backend import CodexBackend, CodexCliBackend, DryRunBackend
from system.services.audit_log import AuditLog
from system.services.settings import settings


MODEL_ID = "hermes-codex"
app = FastAPI(title="Hermes OpenAI-Compatible Adapter")


class ChatMessage(BaseModel):
    role: str
    content: str | list[Any] | None = ""


class ChatCompletionRequest(BaseModel):
    model: str = MODEL_ID
    messages: list[ChatMessage] = Field(default_factory=list)
    stream: bool = False
    temperature: float | None = None


def _backend():
    if settings.worker_backend in {"codex-api", "codex"}:
        return CodexBackend()
    if settings.worker_backend == "codex-cli":
        return CodexCliBackend()
    return DryRunBackend()


def _text_content(content: str | list[Any] | None) -> str:
    if isinstance(content, str):
        return content
    if not content:
        return ""
    parts = []
    for item in content:
        if isinstance(item, dict):
            if item.get("type") == "text":
                parts.append(str(item.get("text", "")))
            elif "text" in item:
                parts.append(str(item["text"]))
    return "\n".join(part for part in parts if part)


def _prompt_from_messages(messages: list[ChatMessage]) -> tuple[str, str]:
    system_parts = []
    prompt_parts = []
    for message in messages:
        text = _text_content(message.content).strip()
        if not text:
            continue
        if message.role == "system":
            system_parts.append(text)
        else:
            prompt_parts.append(f"{message.role}: {text}")
    system = "\n\n".join(system_parts) or HERMES_SYSTEM_PROMPT
    prompt = "\n\n".join(prompt_parts).strip()
    return system, prompt


async def _authorize(authorization: str | None) -> None:
    expected = getattr(settings, "hermes_api_key", "")
    if not expected:
        return
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="Invalid Hermes API key")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "model": MODEL_ID}


@app.get("/v1/models")
async def models(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    await _authorize(authorization)
    return {
        "object": "list",
        "data": [
            {
                "id": MODEL_ID,
                "object": "model",
                "created": 0,
                "owned_by": "hermes",
            }
        ],
    }


@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest, authorization: str | None = Header(default=None)
) -> JSONResponse:
    await _authorize(authorization)
    if request.stream:
        raise HTTPException(status_code=400, detail="Streaming is not enabled for this adapter yet")
    system, prompt = _prompt_from_messages(request.messages)
    if not prompt:
        prompt = "Report Hermes operational status."

    audit = AuditLog()
    hermes = HermesCoordinator.create(backend=_backend())
    audit.write(agent="open-webui-adapter", action="chat_completion", result="started", model=request.model)
    try:
        response = await hermes.backend.complete(prompt, system=system)
    except Exception as exc:
        audit.write(agent="open-webui-adapter", action="chat_completion", result="failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    audit.write(agent="open-webui-adapter", action="chat_completion", result="ok", model=request.model)
    now = int(time.time())
    return JSONResponse(
        {
            "id": f"chatcmpl-hermes-{now}",
            "object": "chat.completion",
            "created": now,
            "model": MODEL_ID,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": response},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }
    )
