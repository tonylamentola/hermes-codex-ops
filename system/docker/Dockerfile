FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OPS_ROOT=/app

WORKDIR /app
COPY pyproject.toml README.md ./
COPY system ./system
RUN pip install --no-cache-dir .
COPY config ./config
COPY docs ./docs

CMD ["python", "-m", "system.hermes.main", "status"]
