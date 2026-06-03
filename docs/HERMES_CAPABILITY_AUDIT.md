# Hermes Capability Audit

This repo is a durable Codex operations layer. It is not, by itself, the full
public Nous Hermes Agent runtime.

## Expected From Public Hermes Agent

Public Hermes Agent materials describe:

- durable Kanban or lane-based orchestration across Codex, Claude Code, Gemini
  CLI, and other agents
- plugin and MCP integration
- reusable/on-the-fly skill curation
- provider proxying for tools that expect an OpenAI-compatible endpoint
- optional self-evolution workflows that optimize skills, prompts, tool
  descriptions, and code through evaluation loops

## Current Repo After This Audit

Implemented here:

- durable queue, memory, logs, Telegram controls, context routing, and worker
  dispatch
- explicit capability audit through `python -m system.hermes.main audit-capabilities`
- broad task decomposition through `python -m system.hermes.main plan "..."`
- enqueueable root plans through `python -m system.hermes.main plan "..." --enqueue`
- named worker lanes:
  - `codex-research`
  - `codex-implementation`
  - `codex-verification`
  - `codex-docs`
  - `codex-improvement`
- Telegram commands:
  - `/plan TASK SUMMARY`
  - `/audit_capabilities`

Still external to this repo:

- installing/running the public `hermes-agent` package
- native Hermes Agent subagents, plugins, Curator, proxy, and self-evolution
  evaluator loops
- real isolated worker pools for each named lane; this repo now exposes the
  lanes, but the VPS process manager still needs to run one worker per lane

## Operator Pattern

Use `/plan` or `main plan --enqueue` for broad tasks. The root task becomes
`planned`; executable subtasks are queued into named lanes. Run one worker per
lane when you want true parallelism:

```bash
python -m system.services.worker --agent codex-research
python -m system.services.worker --agent codex-implementation
python -m system.services.worker --agent codex-verification
python -m system.services.worker --agent codex-improvement
```

Use `codex-improvement` tasks for repeatable gaps: creating or updating
`AGENTS.md`, project `SKILL.md` files, docs, prompts, or checks.
