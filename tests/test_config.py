import json
from pathlib import Path

from system.services.config import load_repositories


def test_load_repositories_from_json(tmp_path: Path) -> None:
    path = tmp_path / "repos.json"
    path.write_text(
        json.dumps(
            {
                "repositories": [
                    {
                        "owner": "owner",
                        "name": "repo",
                        "default_branch": "trunk",
                        "deployment_provider": "docker",
                        "deployment_url": "https://example.com",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    repos = load_repositories(path)

    assert len(repos) == 1
    assert repos[0].slug == "owner/repo"
    assert repos[0].default_branch == "trunk"
    assert repos[0].healthcheck_url == "https://example.com"
