from system.services.ai_backend import CodexCliBackend


def test_codex_cli_backend_name() -> None:
    assert CodexCliBackend().name == "codex-cli"
