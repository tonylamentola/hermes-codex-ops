from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from system.services.audit_log import AuditLog
from system.services.memory import MemoryStore
from system.services.settings import settings


@dataclass(frozen=True)
class RouteProject:
    id: str
    name: str
    domain: str
    aliases: list[str]
    repo_cache_path: str = ""
    workspace_path: str = ""
    include_files: list[str] | None = None
    context_roots: list[str] | None = None
    never_include_domains: list[str] | None = None


def _routing_path(path: Path | None = None) -> Path:
    return path or settings.root / "config" / "context-routing.json"


def _example_path() -> Path:
    return settings.root / "config" / "context-routing.example.json"


def load_routing_manifest(path: Path | None = None) -> dict[str, Any]:
    source = _routing_path(path)
    if not source.exists():
        source = _example_path()
    if not source.exists():
        return {"version": 1, "projects": []}
    return json.loads(source.read_text(encoding="utf-8"))


def _project_from_dict(item: dict[str, Any]) -> RouteProject:
    return RouteProject(
        id=str(item["id"]),
        name=str(item.get("name") or item["id"]),
        domain=str(item.get("domain") or "general"),
        aliases=[str(alias).lower() for alias in item.get("aliases", [])],
        repo_cache_path=str(item.get("repoCachePath") or item.get("repo_cache_path") or ""),
        workspace_path=str(item.get("workspacePath") or item.get("workspace_path") or ""),
        include_files=list(item.get("includeFiles") or item.get("include_files") or []),
        context_roots=list(item.get("contextRoots") or item.get("context_roots") or []),
        never_include_domains=list(item.get("neverIncludeDomains") or item.get("never_include_domains") or []),
    )


def _candidate_roots(project: RouteProject) -> list[Path]:
    roots: list[Path] = []
    if project.repo_cache_path:
        path = Path(project.repo_cache_path)
        roots.append(path if path.is_absolute() else settings.root / path)
    if project.workspace_path:
        roots.append(Path(project.workspace_path))
    return roots


def _read_limited(path: Path, max_chars: int = 1800) -> str:
    try:
        if not path.is_file():
            return ""
        return path.read_text(encoding="utf-8")[:max_chars]
    except OSError:
        return ""


def _file_context(project: RouteProject) -> list[dict[str, str]]:
    files: list[dict[str, str]] = []
    seen: set[str] = set()
    for root in _candidate_roots(project):
        for relative in project.include_files or []:
            path = root / relative
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            text = _read_limited(path)
            if text:
                files.append({"path": str(path), "relativePath": relative, "content": text})
        for relative_root in project.context_roots or []:
            folder = root / relative_root
            if not folder.is_dir():
                continue
            for path in sorted(folder.glob("*/niche.json"))[:12]:
                key = str(path)
                if key in seen:
                    continue
                seen.add(key)
                text = _read_limited(path, max_chars=1200)
                if text:
                    files.append({"path": str(path), "relativePath": str(path.relative_to(root)), "content": text})
    return files


class ContextRouter:
    def __init__(
        self,
        *,
        memory: MemoryStore | None = None,
        audit: AuditLog | None = None,
        manifest_path: Path | None = None,
    ) -> None:
        self.memory = memory or MemoryStore()
        self.audit = audit or AuditLog()
        self.manifest = load_routing_manifest(manifest_path)
        self.projects = [_project_from_dict(item) for item in self.manifest.get("projects", [])]

    def resolve(self, request: str, *, project_id: str | None = None) -> dict[str, Any]:
        text = request.lower()
        scored: list[tuple[int, RouteProject, list[str]]] = []
        for project in self.projects:
            hits: list[str] = []
            if project_id and project.id == project_id:
                hits.append("explicit project id")
            for alias in [project.id.lower(), project.name.lower(), *project.aliases]:
                if alias and alias in text:
                    hits.append(alias)
            score = 100 if project_id and project.id == project_id else 0
            score += 10 * len(set(hits))
            if score:
                scored.append((score, project, sorted(set(hits))))

        scored.sort(key=lambda item: item[0], reverse=True)
        selected = scored[0][1] if scored else None
        confidence = "none"
        needs_clarification = True
        if selected:
            runner_up = scored[1][0] if len(scored) > 1 else 0
            if scored[0][0] >= 100 or scored[0][0] >= runner_up + 10:
                confidence = "high"
                needs_clarification = False
            else:
                confidence = "low"

        if not selected:
            default_id = self.manifest.get("defaultProjectId")
            selected = next((project for project in self.projects if project.id == default_id), None)

        context_files = _file_context(selected) if selected else []
        packet = {
            "project": {
                "id": selected.id,
                "name": selected.name,
                "domain": selected.domain,
                "workspacePath": selected.workspace_path,
                "repoCachePath": selected.repo_cache_path,
                "neverIncludeDomains": selected.never_include_domains or [],
            }
            if selected
            else None,
            "confidence": confidence,
            "needsClarification": needs_clarification,
            "matched": [{"projectId": item[1].id, "score": item[0], "hits": item[2]} for item in scored[:5]],
            "contextFiles": context_files,
            "memory": {
                "contextPack": self.memory.read_markdown("summaries/context-pack.md", max_chars=1800),
                "activeProjects": self.memory.read_markdown("active-projects.md", max_chars=1200),
                "agentStatus": self.memory.read_markdown("agent-status.md", max_chars=1000),
            },
            "rules": [
                "Use only context matching the selected project/domain.",
                "Ask one clarifying question when needsClarification is true.",
                "Do not inject outreach/email context into game-dev tasks.",
                "Do not inject game-dev context into outreach tasks.",
                "Write important results back to the dashboard/task ledger/memory before marking complete.",
            ],
        }
        self.audit.write(
            agent="context-router",
            action="resolve",
            result="clarify" if needs_clarification else "ok",
            project_id=selected.id if selected else "",
            domain=selected.domain if selected else "",
            confidence=confidence,
        )
        return packet


def context_packet_to_markdown(packet: dict[str, Any]) -> str:
    project = packet.get("project") or {}
    lines = [
        "HERMES_CONTEXT_PACKET",
        "",
        f"Project: {project.get('name', 'unknown')} ({project.get('id', 'unknown')})",
        f"Domain: {project.get('domain', 'unknown')}",
        f"Confidence: {packet.get('confidence')}",
        f"Needs clarification: {packet.get('needsClarification')}",
        f"Workspace: {project.get('workspacePath', '')}",
        "",
        "Rules:",
        *[f"- {rule}" for rule in packet.get("rules", [])],
    ]
    files = packet.get("contextFiles") or []
    if files:
        lines.extend(["", "Context files:"])
        for item in files:
            lines.extend([f"\n## {item.get('relativePath')}", item.get("content", "")])
    return "\n".join(lines)
