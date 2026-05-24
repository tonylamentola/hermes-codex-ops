from __future__ import annotations

import base64
import subprocess
from pathlib import Path

from system.services.audit_log import AuditLog
from system.services.config import RepositoryConfig, load_repositories
from system.services.settings import settings


def _auth_header() -> str | None:
    if not settings.github_token:
        return None
    token = base64.b64encode(f"x-access-token:{settings.github_token}".encode("utf-8")).decode("ascii")
    return f"AUTHORIZATION: Basic {token}"


def _run_git(args: list[str], *, cwd: Path | None = None) -> str:
    command = ["git"]
    header = _auth_header()
    if header:
        command.extend(["-c", f"http.https://github.com/.extraheader={header}"])
    command.extend(args)
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def _remote_url(repo: RepositoryConfig) -> str:
    return f"https://github.com/{repo.owner}/{repo.name}.git"


def sync_repo(repo: RepositoryConfig, *, root: Path | None = None) -> dict[str, str]:
    cache_root = root or settings.root / "repos"
    cache_root.mkdir(parents=True, exist_ok=True)
    path = cache_root / repo.name
    url = _remote_url(repo)

    if (path / ".git").exists():
        _run_git(["remote", "set-url", "origin", url], cwd=path)
        _run_git(["fetch", "--prune", "origin", repo.default_branch], cwd=path)
        _run_git(["checkout", repo.default_branch], cwd=path)
        _run_git(["pull", "--ff-only", "origin", repo.default_branch], cwd=path)
        action = "updated"
    else:
        if path.exists():
            backup = path.with_name(f"{path.name}.not-a-git-backup")
            if backup.exists():
                raise RuntimeError(f"Refusing to overwrite existing backup path: {backup}")
            path.rename(backup)
        _run_git(["clone", "--branch", repo.default_branch, url, str(path)])
        action = "cloned"

    sha = _run_git(["rev-parse", "--short", "HEAD"], cwd=path)
    return {"slug": repo.slug, "path": str(path), "branch": repo.default_branch, "sha": sha, "action": action}


def main() -> None:
    audit = AuditLog()
    repos = load_repositories()
    synced = []
    failures = []
    for repo in repos:
        try:
            synced.append(sync_repo(repo))
        except Exception as exc:
            failures.append({"slug": repo.slug, "error": str(exc)})

    audit.write(
        agent="repo-cache-sync",
        action="sync",
        result="failed" if failures else "ok",
        synced=len(synced),
        failures=len(failures),
        repos=synced,
        error="; ".join(f"{item['slug']}: {item['error']}" for item in failures) if failures else None,
    )
    if failures:
        raise SystemExit(f"Repo cache sync failed for {len(failures)} repo(s): {failures}")
    print(f"Synced {len(synced)} repo cache(s).")
    for item in synced:
        print(f"- {item['action']}: {item['slug']} {item['branch']} {item['sha']}")


if __name__ == "__main__":
    main()
