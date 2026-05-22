#!/usr/bin/env bash
set -euo pipefail

ROOT="${OPS_ROOT:-/opt/hermes-codex-ops}"
USER_NAME="${HERMES_SYSTEMD_USER:-root}"
GROUP_NAME="${HERMES_SYSTEMD_GROUP:-root}"

if [[ ! -d "$ROOT/.venv" ]]; then
  echo "Missing virtualenv at $ROOT/.venv. Run system/scripts/bootstrap_ubuntu.sh first." >&2
  exit 1
fi

install_unit() {
  local name="$1"
  local command="$2"
  cat >"/etc/systemd/system/${name}.service" <<UNIT
[Unit]
Description=Hermes Codex Ops ${name}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${USER_NAME}
Group=${GROUP_NAME}
WorkingDirectory=${ROOT}
EnvironmentFile=${ROOT}/.env
ExecStart=/bin/bash -lc '${command}'
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIT
}

install_unit "hermes-telegram" "source ${ROOT}/.venv/bin/activate && python -m system.telegram.bot"
install_unit "hermes-worker" "source ${ROOT}/.venv/bin/activate && python -m system.services.worker"
install_unit "hermes-openai-adapter" "source ${ROOT}/.venv/bin/activate && uvicorn system.hermes.openai_adapter:app --host 172.17.0.1 --port 8010"
install_unit "hermes-watcher-queue" "source ${ROOT}/.venv/bin/activate && while true; do python -m system.watchers.queue_watcher; sleep 300; done"
install_unit "hermes-watcher-stalled" "source ${ROOT}/.venv/bin/activate && while true; do python -m system.watchers.stalled_task_watcher; sleep 300; done"
install_unit "hermes-watcher-memory" "source ${ROOT}/.venv/bin/activate && while true; do python -m system.watchers.memory_integrity_watcher; sleep 600; done"
install_unit "hermes-watcher-memory-compression" "source ${ROOT}/.venv/bin/activate && while true; do python -m system.watchers.memory_compression_watcher; sleep 1800; done"
install_unit "hermes-watcher-github" "source ${ROOT}/.venv/bin/activate && while true; do python -m system.watchers.github_sync_watcher; sleep 900; done"
install_unit "hermes-watcher-deployments" "source ${ROOT}/.venv/bin/activate && while true; do python -m system.watchers.deployment_watcher; sleep 300; done"

systemctl daemon-reload
systemctl enable \
  hermes-telegram.service \
  hermes-worker.service \
  hermes-openai-adapter.service \
  hermes-watcher-queue.service \
  hermes-watcher-stalled.service \
  hermes-watcher-memory.service \
  hermes-watcher-memory-compression.service \
  hermes-watcher-github.service \
  hermes-watcher-deployments.service

echo "Installed Hermes Codex Ops systemd units for ${ROOT}."
