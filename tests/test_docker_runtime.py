from pathlib import Path
import re


def test_docker_image_installs_codex_cli() -> None:
    dockerfile = Path("system/docker/Dockerfile").read_text(encoding="utf-8")

    assert "https://chatgpt.com/codex/install.sh" in dockerfile
    assert "codex --version" in dockerfile
    assert "find /app/.codex /root/.codex" in dockerfile
    assert "readlink -f \"$CODEX_BIN\"" in dockerfile
    assert "install -m 0755 \"$CODEX_BIN\" /usr/local/bin/codex" in dockerfile
    assert "CODEX_HOME=/app/.codex" in dockerfile
    assert "ENTRYPOINT [\"/usr/local/bin/hermes-docker-entrypoint\"]" in dockerfile
    assert "/root/.local/bin" in dockerfile


def test_docker_entrypoint_copies_auth_to_writable_codex_home() -> None:
    entrypoint = Path("system/docker/entrypoint.sh").read_text(encoding="utf-8")

    assert "CODEX_AUTH_SOURCE" in entrypoint
    assert "/codex-auth" in entrypoint
    assert "auth.json" in entrypoint
    assert "config.toml" in entrypoint
    assert "exec \"$@\"" in entrypoint


def service_block(compose: str, service: str) -> str:
    match = re.search(rf"^  {re.escape(service)}\n(?P<body>(?:    .*\n|\n)+)", compose, flags=re.MULTILINE)
    assert match is not None, service
    return match.group(0)


def test_compose_mounts_codex_login_for_codex_callers() -> None:
    compose = Path("system/docker/docker-compose.yml").read_text(encoding="utf-8")

    assert "/root/.codex:/root/.codex:ro" not in compose
    assert compose.count("/root/.codex:/codex-auth:ro") >= 4
    for service in ("telegram:", "worker:", "watcher-memory-compression:"):
        block = service_block(compose, service)
        assert "/root/.codex:/codex-auth:ro" in block
