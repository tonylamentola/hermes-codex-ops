from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from system.services.audit_log import AuditLog
from system.services.memory import MemoryStore
from system.services.settings import settings


DEFAULT_CODEX_JOBS_PATH = Path("/Users/anthonylamentola/cued/telegram-codex-bridge/jobs.json")
ACTIVE_STATUSES = {"in_progress", "pending", "waiting_for_review", "waiting_for_selection", "blocked", "failed"}


def _jobs_path() -> Path:
    return Path(getattr(settings, "codex_jobs_path", "") or DEFAULT_CODEX_JOBS_PATH).expanduser()


def _as_jobs_list(raw: Any) -> list[dict[str, Any]]:
    jobs = raw.get("jobs", raw) if isinstance(raw, dict) else raw
    if isinstance(jobs, dict):
        return [dict({"id": key}, **value) for key, value in jobs.items() if isinstance(value, dict)]
    if isinstance(jobs, list):
        return [job for job in jobs if isinstance(job, dict)]
    return []


def _clean(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback


def _job_summary(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _clean(job.get("id")),
        "title": _clean(job.get("title"), _clean(job.get("id"), "Untitled job")),
        "status": _clean(job.get("status"), "unknown"),
        "cwd": _clean(job.get("cwd"), "unknown"),
        "current_step": _clean(job.get("currentStep")),
        "next_action": _clean(job.get("nextAction")),
        "updated_at": _clean(job.get("updatedAt"), _clean(job.get("updated_at"))),
    }


def load_active_codex_jobs(path: Path | None = None) -> list[dict[str, Any]]:
    source = path or _jobs_path()
    raw = json.loads(source.read_text(encoding="utf-8"))
    jobs = [_job_summary(job) for job in _as_jobs_list(raw)]
    return [job for job in jobs if job["status"] != "completed"]


def summarize_jobs(jobs: list[dict[str, Any]], *, limit_per_project: int = 8) -> dict[str, Any]:
    by_project: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for job in jobs:
        by_project[job["cwd"]].append(job)

    projects = []
    for cwd in sorted(by_project):
        project_jobs = sorted(
            by_project[cwd],
            key=lambda item: (item["status"] not in ACTIVE_STATUSES, item["updated_at"], item["id"]),
            reverse=True,
        )
        projects.append(
            {
                "cwd": cwd,
                "total_open_jobs": len(project_jobs),
                "status_counts": dict(Counter(job["status"] for job in project_jobs)),
                "jobs": project_jobs[:limit_per_project],
            }
        )

    return {
        "total_open_jobs": len(jobs),
        "status_counts": dict(Counter(job["status"] for job in jobs)),
        "projects": projects,
    }


def markdown_summary(summary: dict[str, Any], *, source_path: Path) -> str:
    lines = [
        f"- Source: `{source_path}`",
        f"- Open jobs: `{summary['total_open_jobs']}`",
        f"- Status counts: `{json.dumps(summary['status_counts'], sort_keys=True)}`",
        "",
    ]
    for project in summary["projects"]:
        lines.append(f"### {project['cwd']}")
        lines.append(f"- Open jobs: `{project['total_open_jobs']}`")
        lines.append(f"- Status counts: `{json.dumps(project['status_counts'], sort_keys=True)}`")
        for job in project["jobs"]:
            lines.append(
                f"- `{job['status']}` `{job['id']}`: {job['title']}\n"
                f"  - Current: {job['current_step'] or 'Not recorded'}\n"
                f"  - Next: {job['next_action'] or 'Not recorded'}"
            )
        lines.append("")
    return "\n".join(lines).strip()


@dataclass
class CodexJobSync:
    memory: MemoryStore
    audit: AuditLog
    source_path: Path

    @classmethod
    def create(cls, source_path: Path | None = None) -> "CodexJobSync":
        return cls(memory=MemoryStore(), audit=AuditLog(), source_path=source_path or _jobs_path())

    def sync(self) -> dict[str, Any]:
        self.memory.ensure_baseline()
        jobs = load_active_codex_jobs(self.source_path)
        summary = summarize_jobs(jobs)
        self.memory.write_json_state("projects/codex-jobs.json", summary)
        self.memory.append_markdown(
            "active-projects.md",
            "Codex job tracker sync",
            markdown_summary(summary, source_path=self.source_path),
        )
        self.audit.write(
            agent="codex-job-sync",
            action="sync",
            result="ok",
            source=str(self.source_path),
            open_jobs=summary["total_open_jobs"],
        )
        return summary
