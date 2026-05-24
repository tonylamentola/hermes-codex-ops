# Context Routing

Hermes is the shared context router for Codex, Telegram, Open WebUI, dashboard tasks, and VPS workers.

Before meaningful work, resolve the project/domain context:

```bash
cd /opt/hermes-codex-ops
. .venv/bin/activate
python -m system.scripts.hermes_context "Fix the Light Bringers sprite animation"
```

The response tells the operator or worker:

- project
- domain
- workspace/repo
- files to read
- domains that must not be included
- whether Hermes needs a clarifying question

Do not mix context across domains unless the user explicitly asks for cross-project analysis. A game sprite task must not receive outreach leads. A septic lead task must not receive game asset rules.

Routing lives in `config/context-routing.json`. If that file is missing, Hermes falls back to `config/context-routing.example.json`.
