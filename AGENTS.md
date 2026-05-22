# Agent Instructions

This repository implements a persistent AI operations platform. Preserve these architectural boundaries:

- Hermes coordinates, routes, supervises, summarizes, and dispatches.
- Hermes must not own permanent memory, queues, logs, deployments, GitHub sync, monitoring, or Telegram state internally.
- Durable state must remain human-readable or queryable with standard tools.
- Logs are append-only JSONL.
- Memory updates are timestamped Markdown entries or explicit JSON state files.
- Queue state must survive restarts and be exported to human-readable JSON.

Before changing behavior, check:

- [docs/SYSTEM_OVERVIEW.md](/Users/anthonylamentola/hermes-codex-ops/docs/SYSTEM_OVERVIEW.md)
- [docs/MEMORY_RULES.md](/Users/anthonylamentola/hermes-codex-ops/docs/MEMORY_RULES.md)
- [docs/QUEUE_RULES.md](/Users/anthonylamentola/hermes-codex-ops/docs/QUEUE_RULES.md)

Never create uncontrolled Git commits. Any commit must have an explicit human-approved summary.
