from __future__ import annotations

import asyncio

from system.services.audit_log import AuditLog
from system.services.config import dump_repository_state, load_repositories
from system.services.github import GitHubService
from system.services.memory import MemoryStore
from system.services.settings import settings
from system.watchers.common import notify_telegram_async


async def run() -> None:
    audit = AuditLog()
    memory = MemoryStore()
    repos = load_repositories()
    if not repos:
        audit.write(agent="github-sync-watcher", action="scan", result="skipped", reason="missing config/repos.json")
        return
    if not settings.github_token:
        audit.write(agent="github-sync-watcher", action="scan", result="skipped", reason="missing GITHUB_TOKEN")
        return

    service = GitHubService(audit)
    states = []
    failures = []
    for repo in repos:
        try:
            metadata = await service.repository(repo.owner, repo.name)
            branch = await service.branch(repo.owner, repo.name, repo.default_branch)
            commits = await service.latest_commits(repo.owner, repo.name, repo.default_branch)
            latest = commits[0] if commits else {}
            commit = latest.get("commit", {})
            states.append(
                {
                    "slug": repo.slug,
                    "default_branch": repo.default_branch,
                    "private": metadata.get("private", False),
                    "open_issues": metadata.get("open_issues_count", 0),
                    "pushed_at": metadata.get("pushed_at", ""),
                    "branch_sha": branch.get("commit", {}).get("sha", ""),
                    "latest_commit_sha": latest.get("sha", ""),
                    "latest_commit_message": commit.get("message", "").splitlines()[0] if commit else "",
                    "latest_commit_author": commit.get("author", {}).get("name", "") if commit else "",
                    "latest_commit_date": commit.get("author", {}).get("date", "") if commit else "",
                }
            )
        except Exception as exc:
            failures.append({"slug": repo.slug, "error": str(exc)})

    memory.write_json_state("github-state.json", dump_repository_state(states))
    if states:
        lines = [
            f"- `{state['slug']}` `{state['default_branch']}` {state['latest_commit_sha'][:8]} "
            f"{state['latest_commit_message']} ({state['latest_commit_date']})"
            for state in states
        ]
        memory.append_markdown("github-state.md", "GitHub sync", "\n".join(lines))
    if failures:
        memory.append_markdown(
            "github-state.md",
            "GitHub sync failures",
            "\n".join(f"- `{item['slug']}`: {item['error']}" for item in failures),
        )
        await notify_telegram_async(f"GitHub sync failures: {len(failures)} repo(s). Check memory/github-state.md")
    audit.write(
        agent="github-sync-watcher",
        action="scan",
        result="failed" if failures and not states else "ok",
        repositories=len(states),
        failures=len(failures),
    )


if __name__ == "__main__":
    asyncio.run(run())
