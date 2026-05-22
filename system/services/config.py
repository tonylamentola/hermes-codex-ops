from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from system.services.settings import settings


@dataclass(frozen=True)
class RepositoryConfig:
    owner: str
    name: str
    default_branch: str = "main"
    deployment_provider: str = "manual"
    deployment_url: str = ""
    healthcheck_url: str = ""

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.name}"


def load_repositories(path: Path | None = None) -> list[RepositoryConfig]:
    path = path or settings.root / "config" / "repos.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    repos: list[RepositoryConfig] = []
    for item in data.get("repositories", []):
        repos.append(
            RepositoryConfig(
                owner=item["owner"],
                name=item["name"],
                default_branch=item.get("default_branch", "main"),
                deployment_provider=item.get("deployment_provider", "manual"),
                deployment_url=item.get("deployment_url", ""),
                healthcheck_url=item.get("healthcheck_url", item.get("deployment_url", "")),
            )
        )
    return repos


def dump_repository_state(repositories: list[dict[str, Any]]) -> dict[str, Any]:
    return {"repositories": repositories}
