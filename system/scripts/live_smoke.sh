#!/usr/bin/env bash
set -euo pipefail

cd "${APP_DIR:-/opt/hermes-codex-ops}"

source .venv/bin/activate

python -m system.scripts.healthcheck
python -m system.hermes.main submit "Live smoke task from VPS" --priority 9
python -m system.services.worker --once
python -m system.watchers.queue_watcher
python -m system.watchers.memory_compression_watcher
python -m system.scripts.healthcheck

echo "Live smoke complete. Check Telegram /status if bot secrets are configured."
