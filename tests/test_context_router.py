from pathlib import Path

from system.services.context_router import ContextRouter
from system.services.memory import MemoryStore


def test_context_router_keeps_game_out_of_outreach(tmp_path: Path) -> None:
    manifest = tmp_path / "context-routing.json"
    manifest.write_text(
        """
{
  "version": 1,
  "projects": [
    {"id": "outreach-dashboard", "name": "Outreach Dashboard", "domain": "outreach", "aliases": ["lead", "septic"], "neverIncludeDomains": ["game-dev"]},
    {"id": "light-bringers", "name": "Light Bringers", "domain": "game-dev", "aliases": ["sprite", "combat"], "neverIncludeDomains": ["outreach"]}
  ]
}
""",
        encoding="utf-8",
    )
    router = ContextRouter(memory=MemoryStore(root=tmp_path / "memory"), manifest_path=manifest)

    game = router.resolve("Fix the Light Bringers sprite animation")
    outreach = router.resolve("Generate septic leads and flyer previews")

    assert game["project"]["id"] == "light-bringers"
    assert game["project"]["domain"] == "game-dev"
    assert "outreach" in game["project"]["neverIncludeDomains"]
    assert outreach["project"]["id"] == "outreach-dashboard"
    assert outreach["project"]["domain"] == "outreach"


def test_context_router_marks_ambiguous_request_for_clarification(tmp_path: Path) -> None:
    manifest = tmp_path / "context-routing.json"
    manifest.write_text(
        """
{
  "version": 1,
  "defaultProjectId": "hermes-ops",
  "projects": [
    {"id": "hermes-ops", "name": "Hermes Ops", "domain": "ops", "aliases": ["hermes"]},
    {"id": "outreach-dashboard", "name": "Outreach Dashboard", "domain": "outreach", "aliases": ["dashboard"]},
    {"id": "light-bringers", "name": "Light Bringers", "domain": "game-dev", "aliases": ["dashboard"]}
  ]
}
""",
        encoding="utf-8",
    )
    router = ContextRouter(memory=MemoryStore(root=tmp_path / "memory"), manifest_path=manifest)

    packet = router.resolve("fix the dashboard")

    assert packet["needsClarification"] is True
    assert packet["confidence"] == "low"


def test_context_router_routes_website_homepage_separately(tmp_path: Path) -> None:
    manifest = tmp_path / "context-routing.json"
    manifest.write_text(
        """
{
  "version": 1,
  "projects": [
    {"id": "simpleweb", "name": "SimpleWeb", "domain": "website-design", "aliases": ["website", "homepage"]},
    {"id": "outreach-dashboard", "name": "Outreach Dashboard", "domain": "outreach", "aliases": ["lead", "flyer"]},
    {"id": "light-bringers", "name": "Light Bringers", "domain": "game-dev", "aliases": ["sprite"]}
  ]
}
""",
        encoding="utf-8",
    )
    router = ContextRouter(memory=MemoryStore(root=tmp_path / "memory"), manifest_path=manifest)

    packet = router.resolve("fix a website homepage")

    assert packet["project"]["id"] == "simpleweb"
    assert packet["project"]["domain"] == "website-design"
