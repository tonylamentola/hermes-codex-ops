# Open WebUI Trial

Open WebUI is an optional interface layer for Hermes Codex Ops. It must not own Hermes memory, queue state, logs, deployments, or GitHub state.

## Role

- Open WebUI: browser/mobile chat console and future rich dashboard.
- Hermes: orchestration, routing, summaries, task dispatch.
- Existing durable systems: `/memory`, `/tasks`, `/logs`, `/config`, and GitHub remain the source of truth.

## VPS Trial Service

Start:

```bash
cd /opt/hermes-codex-ops
bash system/scripts/open_webui.sh start
```

Status:

```bash
bash system/scripts/open_webui.sh status
```

Logs:

```bash
bash system/scripts/open_webui.sh logs
```

Stop:

```bash
bash system/scripts/open_webui.sh stop
```

Runtime details:

- Container: `open-webui`
- Image: `ghcr.io/open-webui/open-webui:main`
- Port: `3000 -> 8080`
- Data volume: `open-webui`
- Host bridge alias: `host.docker.internal` for reaching Hermes services on the VPS host.

## Mobile Notes

Open WebUI works in a mobile browser. For a real phone install/PWA experience, put it behind HTTPS on a domain or trusted reverse proxy. Raw `http://IP:3000` is fine for a quick trial, but not the long-term mobile route.

Native mobile clients such as Conduit can also connect to a self-hosted Open WebUI server.

## Integration Path

Do not duplicate Hermes internals inside Open WebUI. Add Hermes capabilities as explicit tools:

- `get_status`
- `submit_task`
- `list_tasks`
- `approve_task`
- `retry_task`
- `read_memory`
- `tail_logs`

Open WebUI can then become the richer web/mobile console while Telegram remains the fast alert and control channel.

## Hermes Model Adapter

The trial includes a minimal OpenAI-compatible adapter:

```bash
uvicorn system.hermes.openai_adapter:app --host 172.17.0.1 --port 8010
```

Open WebUI can use it as an OpenAI-compatible connection:

- Base URL: `http://host.docker.internal:8010/v1`
- API key: value of `HERMES_API_KEY` if set, otherwise any placeholder.
- Model: `hermes-codex`

The adapter intentionally writes to Hermes audit logs and uses existing Hermes backend settings. It is a bridge, not a new memory/task owner.
