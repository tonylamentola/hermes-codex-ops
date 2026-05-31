from system.services.queue import Task
from system.services.worker import (
    artifact_summary,
    backend_prompt,
    expected_artifacts,
    extract_artifacts,
    merge_artifacts,
    missing_required_artifacts,
    short_task_id,
    task_chat_ids,
)
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

    assert "I saved this as task 12345678" in ack
    assert "Tap Approve" in ack
    assert "Cancel" in ack
    assert "12345678-aaaa-bbbb-cccc-123456789abc" not in ack


def test_short_task_id_is_readable() -> None:
    assert short_task_id(make_task({})) == "12345678"


def test_task_matches_chat_accepts_string_or_int_chat_id() -> None:
    assert _task_matches_chat(make_task({"telegram": {"chat_id": "7272977804"}}), 7272977804)
    assert _task_matches_chat(make_task({"telegram": {"chat_id": 7272977804}}), 7272977804)
    assert not _task_matches_chat(make_task({}), 7272977804)


def test_chat_tasks_sort_newest_first(monkeypatch) -> None:
    from system.telegram import bot

    old = make_task({"telegram": {"chat_id": 7272977804}})
    old.id = "old-task"
    old.updated_at = "2026-05-22T00:00:00+00:00"
    new = make_task({"telegram": {"chat_id": 7272977804}})
    new.id = "new-task"
    new.updated_at = "2026-05-24T00:00:00+00:00"
    monkeypatch.setattr(bot.queue, "list", lambda limit=200: [old, new])

    assert [task.id for task in bot._chat_tasks(7272977804)] == ["new-task", "old-task"]


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

    assert "Task 12345678 - pending" in text
    assert "Do the thing" in text
    assert "Files are not ready yet" in text


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


def test_expected_artifacts_expands_task_id_and_marks_required(tmp_path) -> None:
    task_id = "12345678-aaaa-bbbb-cccc-123456789abc"
    expected = expected_artifacts(
        {
            "artifacts": [
                {"display_path": "tasks/active.json"},
                {"display_path": "artifacts/leads/<task_id>-leads.json"},
            ]
        },
        task_id,
        root=tmp_path,
    )

    assert len(expected) == 1
    assert expected[0]["display_path"] == f"artifacts/leads/{task_id}-leads.json"
    assert expected[0]["required"] is True
    assert expected[0]["exists"] is False


def test_merge_artifacts_preserves_required_missing_state(tmp_path) -> None:
    required_path = tmp_path / "artifacts" / "leads" / "task-leads.json"
    merged = merge_artifacts(
        [{"path": str(required_path), "display_path": "artifacts/leads/task-leads.json", "exists": False, "required": True}],
        [{"path": str(tmp_path / "other.md"), "display_path": "other.md", "exists": True}],
    )

    missing = missing_required_artifacts(merged)

    assert [item["display_path"] for item in missing] == ["artifacts/leads/task-leads.json"]


def test_backend_prompt_names_required_files() -> None:
    prompt = backend_prompt(
        "CONTEXT",
        [{"display_path": "artifacts/leads/task-leads.json"}],
    )

    assert "Create every file below before you finish" in prompt
    assert "artifacts/leads/task-leads.json" in prompt


def test_control_summaries_are_not_real_tasks() -> None:
    assert _is_control_summary("Approve")
    assert _is_control_summary("approved")
    assert _is_control_summary("what's the task")
    assert _is_control_summary("status")
    assert not _is_control_summary("Generate a new shirt in cotton club")


def test_help_text_explains_natural_controls() -> None:
    text = _help_text()

    assert "`status`" in text
    assert "`latest result`" in text
    assert "start with `task:`" in text
