#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/hermes-codex-ops}"

if [[ ! -d "$APP_DIR" ]]; then
  echo "Missing app directory: $APP_DIR"
  echo "Copy or clone hermes-codex-ops to $APP_DIR first."
  exit 1
fi

sudo apt-get update
sudo apt-get install -y \
  ca-certificates \
  curl \
  git \
  jq \
  python3 \
  python3-venv \
  sqlite3

if ! command -v docker >/dev/null 2>&1; then
  sudo apt-get install -y docker.io docker-compose-plugin
fi

cd "$APP_DIR"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example. Fill secrets before live use."
fi

if [[ ! -f config/repos.json ]]; then
  cp config/repos.example.json config/repos.json
  echo "Created config/repos.json from example. Edit monitored repositories before live use."
fi

if [[ ! -f config/control-state.json ]]; then
  cp config/control-state.example.json config/control-state.json
fi

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
python -m system.scripts.init_platform
python -m system.watchers.memory_compression_watcher

echo "Bootstrap complete."
echo "Next: edit $APP_DIR/.env and $APP_DIR/config/repos.json, then run:"
echo "  cd $APP_DIR/system/docker && docker compose up -d --build"
