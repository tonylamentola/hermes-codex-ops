# Memory Rules

Memory must be persistent, inspectable, and portable.

## Files

- `memory/active-projects.md`
- `memory/deployment-history.md`
- `memory/github-state.md`
- `memory/agent-status.md`
- `memory/summaries/handoffs.md`
- `memory/summaries/context-pack.md`
- `memory/summaries/context-pack.json`

## Rules

- Append timestamped entries for important events.
- Do not overwrite important historical logs.
- Use Markdown for narrative summaries.
- Use JSON for structured state that automation needs to read.
- Keep summaries compressed enough for future context injection.
- Store handoff summaries between agent sessions.
- Compress memory into context packs without deleting raw memory.

## Compression

The memory compressor reads durable Markdown memory and writes compact handoff context:

```bash
python -m system.services.memory_compressor
python -m system.watchers.memory_compression_watcher
```

By default, `MEMORY_COMPRESSION_BACKEND=dry-run` creates a deterministic context pack from recent entries. Set `MEMORY_COMPRESSION_BACKEND=codex` to ask Codex to compress the deterministic source into a shorter operational handoff.

Raw memory files are not deleted or rewritten. The generated outputs are:

- `memory/summaries/context-pack.md`
- `memory/summaries/context-pack.json`

## Recovery

If Hermes fails, inspect memory directly:

```bash
less memory/active-projects.md
less memory/summaries/handoffs.md
less memory/summaries/context-pack.md
jq . memory/projects/*.json
```
