FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OPS_ROOT=/app \
    HOME=/app \
    CODEX_HOME=/app/.codex \
    XDG_CONFIG_HOME=/app/.config \
    XDG_CACHE_HOME=/app/.cache \
    PATH=/root/.local/bin:/usr/local/bin:$PATH

WORKDIR /app
RUN mkdir -p /app/.codex /app/.config /app/.cache
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl git ripgrep \
    && curl -fsSL https://chatgpt.com/codex/install.sh | sh \
    && CODEX_BIN="$(command -v codex || find /root/.codex -type f -path '*/bin/codex' -perm /111 | head -n 1)" \
    && test -n "$CODEX_BIN" \
    && CODEX_BIN="$(readlink -f "$CODEX_BIN")" \
    && install -m 0755 "$CODEX_BIN" /usr/local/bin/codex \
    && codex --version \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
COPY system/docker/entrypoint.sh /usr/local/bin/hermes-docker-entrypoint
RUN chmod +x /usr/local/bin/hermes-docker-entrypoint
COPY pyproject.toml README.md ./
COPY system ./system
RUN pip install --no-cache-dir .
COPY config ./config
COPY docs ./docs

ENTRYPOINT ["/usr/local/bin/hermes-docker-entrypoint"]
CMD ["python", "-m", "system.hermes.main", "status"]
