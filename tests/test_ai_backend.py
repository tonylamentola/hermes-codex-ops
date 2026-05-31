from types import SimpleNamespace

from system.services.ai_backend import CodexCliBackend, _terminate_process_group


def test_codex_cli_backend_name() -> None:
    assert CodexCliBackend().name == "codex-cli"


def test_terminate_process_group_tolerates_missing_process() -> None:
    proc = SimpleNamespace(pid=999999999, terminate=lambda: None)
    _terminate_process_group(proc)
