from pathlib import Path

from system.services.audit_log import AuditLog
from system.services.control_state import ControlState


def test_control_state_pause_resume(tmp_path: Path) -> None:
    control = ControlState(path=tmp_path / "control-state.json", audit=AuditLog(tmp_path / "ops.jsonl"))

    paused = control.pause(reason="maintenance", updated_by="test")
    resumed = control.resume(updated_by="test")

    assert paused["paused"] is True
    assert paused["reason"] == "maintenance"
    assert resumed["paused"] is False
    assert control.is_paused() is False


def test_audit_tail_reads_only_recent_records(tmp_path: Path) -> None:
    audit = AuditLog(path=tmp_path / "logs" / "ops.jsonl")
    for idx in range(5):
        audit.write(agent="test", action=f"action-{idx}", result="ok")

    rows = audit.tail(2)

    assert [row["action"] for row in rows] == ["action-3", "action-4"]
