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
- `memory/projects/codex-jobs.json`

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

## Codex Job Sync

Hermes can be caught up on existing Codex work by importing the central Codex job tracker into durable memory:

```bash
python -m system.scripts.sync_codex_jobs
python -m system.services.memory_compressor
```

The source defaults to `CODEX_JOBS_PATH`, or `/Users/anthonylamentola/cued/telegram-codex-bridge/jobs.json` when unset. The sync imports only jobs whose status is not `completed`.

Outputs:

- Appends a timestamped summary to `memory/active-projects.md`
- Writes structured state to `memory/projects/codex-jobs.json`
- Logs the sync to `logs/ops.jsonl`

This is intentionally deterministic and human-readable. It does not import full chat transcripts, hidden state, or opaque memory blobs.

## Recovery

If Hermes fails, inspect memory directly:

```bash
less memory/active-projects.md
less memory/summaries/handoffs.md
less memory/summaries/context-pack.md
jq . memory/projects/*.json
```
