import json
from pathlib import Path

from system.services.codex_job_sync import CodexJobSync, load_active_codex_jobs, markdown_summary, summarize_jobs
from system.services.audit_log import AuditLog
from system.services.memory import MemoryStore


def test_load_active_codex_jobs_supports_keyed_tracker(tmp_path: Path) -> None:
    path = tmp_path / "jobs.json"
    path.write_text(
        json.dumps(
            {
                "jobs": {
                    "done": {"status": "completed", "cwd": "/repo", "title": "Done"},
                    "open": {
                        "status": "in_progress",
                        "cwd": "/repo",
                        "title": "Open",
                        "currentStep": "Working",
                        "nextAction": "Finish",
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    jobs = load_active_codex_jobs(path)

    assert len(jobs) == 1
    assert jobs[0]["id"] == "open"
    assert jobs[0]["current_step"] == "Working"


def test_summarize_jobs_groups_by_project() -> None:
    summary = summarize_jobs(
        [
            {"id": "a", "title": "A", "status": "pending", "cwd": "/repo-a", "current_step": "", "next_action": "", "updated_at": ""},
            {"id": "b", "title": "B", "status": "blocked", "cwd": "/repo-a", "current_step": "", "next_action": "", "updated_at": ""},
            {"id": "c", "title": "C", "status": "failed", "cwd": "/repo-b", "current_step": "", "next_action": "", "updated_at": ""},
        ]
    )

    assert summary["total_open_jobs"] == 3
    assert summary["status_counts"] == {"pending": 1, "blocked": 1, "failed": 1}
    assert [project["cwd"] for project in summary["projects"]] == ["/repo-a", "/repo-b"]


def test_sync_writes_json_and_appends_markdown(tmp_path: Path) -> None:
    jobs_path = tmp_path / "jobs.json"
    jobs_path.write_text(
        json.dumps({"jobs": {"open": {"status": "pending", "cwd": "/repo", "title": "Open"}}}),
        encoding="utf-8",
    )
    memory = MemoryStore(root=tmp_path / "memory")
    sync = CodexJobSync(memory=memory, audit=AuditLog(path=tmp_path / "logs" / "ops.jsonl"), source_path=jobs_path)

    summary = sync.sync()

    assert summary["total_open_jobs"] == 1
    assert "Open" in memory.read_full_markdown("active-projects.md")
    assert memory.read_json_state("projects/codex-jobs.json")["data"]["total_open_jobs"] == 1


def test_markdown_summary_is_human_readable(tmp_path: Path) -> None:
    text = markdown_summary(
        {
            "total_open_jobs": 1,
            "status_counts": {"pending": 1},
            "projects": [
                {
                    "cwd": "/repo",
                    "total_open_jobs": 1,
                    "status_counts": {"pending": 1},
                    "jobs": [
                        {
                            "id": "job-1",
                            "title": "Import job",
                            "status": "pending",
                            "current_step": "Queued",
                            "next_action": "Run it",
                        }
                    ],
                }
            ],
        },
        source_path=tmp_path / "jobs.json",
    )

    assert "### /repo" in text
    assert "`pending` `job-1`: Import job" in text
