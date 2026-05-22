#!/usr/bin/env bash
set -euo pipefail

NAME="${OPEN_WEBUI_CONTAINER_NAME:-open-webui}"
PORT="${OPEN_WEBUI_PORT:-3000}"
VOLUME="${OPEN_WEBUI_VOLUME:-open-webui}"
IMAGE="${OPEN_WEBUI_IMAGE:-ghcr.io/open-webui/open-webui:main}"

usage() {
  cat <<USAGE
Usage: $0 start|stop|status|logs

Environment:
  OPEN_WEBUI_CONTAINER_NAME  default: open-webui
  OPEN_WEBUI_PORT            default: 3000
  OPEN_WEBUI_VOLUME          default: open-webui
  OPEN_WEBUI_IMAGE           default: ghcr.io/open-webui/open-webui:main
USAGE
}

case "${1:-}" in
  start)
    if docker ps -a --format '{{.Names}}' | grep -qx "$NAME"; then
      docker start "$NAME" >/dev/null
    else
      docker run -d \
        --name "$NAME" \
        --restart unless-stopped \
        -p "${PORT}:8080" \
        -v "${VOLUME}:/app/backend/data" \
        "$IMAGE" >/dev/null
    fi
    docker ps --filter "name=${NAME}" --format '{{.Names}} {{.Status}} {{.Ports}}'
    ;;
  stop)
    docker stop "$NAME"
    ;;
  status)
    docker ps -a --filter "name=${NAME}" --format '{{.Names}} {{.Status}} {{.Ports}}'
    ;;
  logs)
    docker logs --tail="${OPEN_WEBUI_LOG_LINES:-100}" "$NAME"
    ;;
  *)
    usage
    exit 2
    ;;
esac
