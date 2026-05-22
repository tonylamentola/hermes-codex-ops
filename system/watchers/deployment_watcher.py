from __future__ import annotations

import asyncio

from system.services.audit_log import AuditLog
from system.services.config import load_repositories
from system.services.memory import MemoryStore
from system.watchers.common import notify_telegram_async


async def check_url(url: str) -> tuple[str, int | None, str]:
    import httpx

    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            response = await client.get(url)
        result = "ok" if response.status_code < 500 else "failed"
        return result, response.status_code, ""
    except Exception as exc:
        return "failed", None, str(exc)


async def run() -> None:
    audit = AuditLog()
    memory = MemoryStore()
    repos = load_repositories()
    targets = [repo for repo in repos if repo.healthcheck_url]
    if not targets:
        memory.append_markdown("deployment-history.md", "Deployment watcher heartbeat", "No healthcheck URLs configured.")
        audit.write(agent="deployment-watcher", action="scan", result="skipped", reason="no healthcheck URLs")
        return

    rows = []
    failures = []
    for repo in targets:
        result, status_code, error = await check_url(repo.healthcheck_url)
        row = {
            "slug": repo.slug,
            "provider": repo.deployment_provider,
            "url": repo.healthcheck_url,
            "result": result,
            "status_code": status_code,
            "error": error,
        }
        rows.append(row)
        if result != "ok":
            failures.append(row)
        audit.write(agent="deployment-watcher", action="healthcheck", **row)

    memory.write_json_state("deployment-state.json", {"deployments": rows})
    memory.append_markdown(
        "deployment-history.md",
        "Deployment scan",
        "\n".join(
            f"- `{row['slug']}` {row['provider']} {row['result']} "
            f"{row['status_code'] or ''} {row['url']}"
            for row in rows
        ),
    )
    if failures:
        await notify_telegram_async(f"Deployment failures: {len(failures)} target(s). Check memory/deployment-history.md")
    audit.write(
        agent="deployment-watcher",
        action="scan",
        result="failed" if failures else "ok",
        checked=len(rows),
        failures=len(failures),
    )


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
