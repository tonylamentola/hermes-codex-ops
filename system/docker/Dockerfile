FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OPS_ROOT=/app \
    PATH=/root/.local/bin:/usr/local/bin:$PATH

WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl git ripgrep \
    && curl -fsSL https://chatgpt.com/codex/install.sh | sh \
    && CODEX_BIN="$(command -v codex || find /root -type f -name codex -perm /111 | head -n 1)" \
    && test -n "$CODEX_BIN" \
    && ln -sf "$CODEX_BIN" /usr/local/bin/codex \
    && codex --version \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md ./
COPY system ./system
RUN pip install --no-cache-dir .
COPY config ./config
COPY docs ./docs

CMD ["python", "-m", "system.hermes.main", "status"]
