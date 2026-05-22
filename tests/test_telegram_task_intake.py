from system.services.queue import Task
from system.services.worker import short_task_id, task_chat_ids
from system.telegram.bot import _task_ack


def make_task(payload: dict) -> Task:
    return Task(
        id="12345678-aaaa-bbbb-cccc-123456789abc",
        timestamp="2026-05-22T00:00:00+00:00",
        assigned_agent="codex",
        priority=5,
        retry_count=0,
        status="pending",
        summary="Do the thing",
        payload=payload,
        updated_at="2026-05-22T00:00:00+00:00",
    )


def test_task_chat_ids_returns_originating_telegram_chat() -> None:
    task = make_task({"telegram": {"chat_id": "7272977804"}})

    assert task_chat_ids(task) == {7272977804}


def test_task_chat_ids_falls_back_without_telegram_payload() -> None:
    assert task_chat_ids(make_task({})) is None
    assert task_chat_ids(make_task({"telegram": {"chat_id": "not-a-number"}})) is None


def test_task_ack_mentions_updates_and_cancel_command() -> None:
    ack = _task_ack("12345678-aaaa-bbbb-cccc-123456789abc")

    assert "Queued task: 12345678" in ack
    assert "starts, completes, fails, or needs approval" in ack
    assert "/cancel 12345678-aaaa-bbbb-cccc-123456789abc" in ack


def test_short_task_id_is_readable() -> None:
    assert short_task_id(make_task({})) == "12345678"
