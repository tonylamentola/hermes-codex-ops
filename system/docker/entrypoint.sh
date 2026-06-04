#!/bin/sh
set -eu

CODEX_WRITABLE_HOME="${CODEX_HOME:-/app/.codex}"
CODEX_AUTH_SOURCE="${CODEX_AUTH_SOURCE:-/codex-auth}"

mkdir -p "$CODEX_WRITABLE_HOME" "${XDG_CONFIG_HOME:-/app/.config}" "${XDG_CACHE_HOME:-/app/.cache}"

if [ -d "$CODEX_AUTH_SOURCE" ]; then
  for name in auth.json config.toml AGENTS.md rules; do
    if [ -e "$CODEX_AUTH_SOURCE/$name" ] && [ ! -e "$CODEX_WRITABLE_HOME/$name" ]; then
      cp -R "$CODEX_AUTH_SOURCE/$name" "$CODEX_WRITABLE_HOME/$name"
    fi
  done
fi

exec "$@"
