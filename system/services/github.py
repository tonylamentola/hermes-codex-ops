from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from system.services.audit_log import AuditLog
from system.services.settings import settings


@dataclass
class GitHubService:
    audit: AuditLog

    def _headers(self) -> dict[str, str]:
        if not settings.github_token:
            raise RuntimeError("GITHUB_TOKEN is required for GitHub API calls")
        return {
            "Authorization": f"Bearer {settings.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def list_repositories(self, owner: str | None = None) -> list[dict[str, Any]]:
        import httpx

        owner = owner or settings.github_owner
        if not owner:
            raise RuntimeError("GITHUB_OWNER is required")
        url = f"https://api.github.com/users/{owner}/repos"
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, headers=self._headers())
            response.raise_for_status()
            repos = response.json()
        self.audit.write(agent="github-sync", action="list_repositories", result="ok", owner=owner, count=len(repos))
        return repos

    async def latest_commits(self, owner: str, repo: str, branch: str = "main") -> list[dict[str, Any]]:
        import httpx

        url = f"https://api.github.com/repos/{owner}/{repo}/commits"
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, headers=self._headers(), params={"sha": branch, "per_page": 10})
            response.raise_for_status()
            commits = response.json()
        self.audit.write(
            agent="github-sync",
            action="latest_commits",
            result="ok",
            owner=owner,
            repo=repo,
            branch=branch,
            count=len(commits),
        )
        return commits

    async def branch(self, owner: str, repo: str, branch: str = "main") -> dict[str, Any]:
        import httpx

        url = f"https://api.github.com/repos/{owner}/{repo}/branches/{branch}"
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, headers=self._headers())
            response.raise_for_status()
            data = response.json()
        self.audit.write(
            agent="github-sync",
            action="branch",
            result="ok",
            owner=owner,
            repo=repo,
            branch=branch,
            sha=data.get("commit", {}).get("sha", ""),
        )
        return data

    async def repository(self, owner: str, repo: str) -> dict[str, Any]:
        import httpx

        url = f"https://api.github.com/repos/{owner}/{repo}"
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, headers=self._headers())
            response.raise_for_status()
            data = response.json()
        self.audit.write(agent="github-sync", action="repository", result="ok", owner=owner, repo=repo)
        return data
