from system.services.queue import Task
from system.services.worker import artifact_summary, extract_artifacts, short_task_id, task_chat_ids
from system.telegram.bot import (
    _details_text,
    _help_text,
    _is_control_summary,
    _task_ack,
    _task_keyboard,
    _task_matches_chat,
)


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
    assert "Tap Approve" in ack
    assert "12345678-aaaa-bbbb-cccc-123456789abc" not in ack


def test_short_task_id_is_readable() -> None:
    assert short_task_id(make_task({})) == "12345678"


def test_task_matches_chat_accepts_string_or_int_chat_id() -> None:
    assert _task_matches_chat(make_task({"telegram": {"chat_id": "7272977804"}}), 7272977804)
    assert _task_matches_chat(make_task({"telegram": {"chat_id": 7272977804}}), 7272977804)
    assert not _task_matches_chat(make_task({}), 7272977804)


def test_task_keyboard_exposes_approve_cancel_details() -> None:
    keyboard = _task_keyboard("12345678-aaaa-bbbb-cccc-123456789abc")

    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert [button.text for button in buttons] == ["Approve", "Cancel", "Details"]
    assert buttons[0].callback_data == "approve:12345678-aaaa-bbbb-cccc-123456789abc"


def test_details_text_is_short_and_readable() -> None:
    text = _details_text(
        make_task(
            {
                "backend": "dry-run",
                "worker_context": "Result text",
                "artifacts": [
                    {
                        "display_path": "shirts/new-shirt.png",
                        "path": "/tmp/new-shirt.png",
                        "exists": False,
                        "kind": "image",
                    }
                ],
            }
        )
    )

    assert "Task 12345678" in text
    assert "Status: pending" in text
    assert "Do the thing" in text
    assert "Backend: dry-run" in text
    assert "missing: shirts/new-shirt.png" in text
    assert "Result preview" in text


def test_extract_artifacts_finds_relative_and_absolute_paths(tmp_path) -> None:
    image = tmp_path / "out" / "shirt.png"
    image.parent.mkdir()
    image.write_bytes(b"png")

    artifacts = extract_artifacts(
        f"Created `{image}` and `assets/missing-shirt.webp`.",
        root=tmp_path,
    )

    assert artifacts[0]["path"] == str(image)
    assert artifacts[0]["exists"] is True
    assert artifacts[0]["kind"] == "image"
    assert any(item["display_path"] == "assets/missing-shirt.webp" for item in artifacts)


def test_artifact_summary_reports_none_and_paths() -> None:
    assert artifact_summary([]) == "Artifacts: none reported."
    text = artifact_summary([{"display_path": "shirt.png", "exists": True}])
    assert "ok: shirt.png" in text


def test_control_summaries_are_not_real_tasks() -> None:
    assert _is_control_summary("Approve")
    assert _is_control_summary("approved")
    assert _is_control_summary("what's the task")
    assert _is_control_summary("status")
    assert not _is_control_summary("Generate a new shirt in cotton club")


def test_help_text_explains_natural_controls() -> None:
    text = _help_text()

    assert "approve / yes / go ahead" in text
    assert "tasks or what's the task" in text
