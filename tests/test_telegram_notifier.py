from pathlib import Path

from system.services.notifier import telegram_upload_path


def test_telegram_upload_path_uses_photo_for_png(tmp_path: Path) -> None:
    image = tmp_path / "preview.png"
    image.write_bytes(b"png")

    upload, endpoint, field = telegram_upload_path(image)

    assert upload == image
    assert endpoint == "sendPhoto"
    assert field == "photo"


def test_telegram_upload_path_falls_back_for_svg_without_renderer(tmp_path: Path, monkeypatch) -> None:
    svg = tmp_path / "preview.svg"
    svg.write_text("<svg />", encoding="utf-8")
    monkeypatch.setattr("system.services.notifier.shutil.which", lambda name: None)

    upload, endpoint, field = telegram_upload_path(svg)

    assert upload == svg
    assert endpoint == "sendDocument"
    assert field == "document"


def test_telegram_upload_path_converts_svg_to_photo(tmp_path: Path, monkeypatch) -> None:
    svg = tmp_path / "preview.svg"
    svg.write_text("<svg />", encoding="utf-8")
    monkeypatch.setattr("system.services.notifier.shutil.which", lambda name: "rsvg-convert")
    monkeypatch.setattr(
        "system.services.notifier._svg_preview_path",
        lambda file_path: tmp_path / "converted.png",
    )

    def fake_run(command, **kwargs):
        output = Path(command[4])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"png")

    monkeypatch.setattr("system.services.notifier.subprocess.run", fake_run)

    upload, endpoint, field = telegram_upload_path(svg)

    assert upload.suffix == ".png"
    assert upload.exists()
    assert endpoint == "sendPhoto"
    assert field == "photo"
