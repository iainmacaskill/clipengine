import httpx
import pytest

from clipengine.edit import textcard
from clipengine.edit.textcard import PRESETS, get_preset, install_fonts

pytestmark = pytest.mark.skipif(not textcard.available(), reason="Pillow not installed")


def test_presets_cover_the_researched_looks():
    assert set(PRESETS) == {
        "clean", "hormozi", "hormozi-green", "beast", "block", "playful"
    }
    assert PRESETS["hormozi"].uppercase          # Hormozi is ALL CAPS
    assert PRESETS["hormozi"].highlight == "#FFD93D"
    assert PRESETS["hormozi-green"].highlight == "#A6FF00"
    # every preset names its font and a highlight colour
    for style in PRESETS.values():
        assert style.font_candidates and style.highlight


def test_get_preset_returns_copy_and_validates():
    a = get_preset("clean")
    a.font_size = 999
    assert PRESETS["clean"].font_size != 999
    with pytest.raises(ValueError, match="unknown style"):
        get_preset("comic-sans")


def test_preset_falls_back_to_system_font(tmp_path, monkeypatch):
    """Preset fonts not installed -> render still works via system bold."""
    monkeypatch.setattr(textcard, "FONT_DIR", str(tmp_path / "nofonts"))
    path, _h = textcard.render_text_card(
        "FALLBACK *TEST*", str(tmp_path / "c.png"), 700, style=get_preset("hormozi")
    )
    from PIL import Image

    assert Image.open(path).getbbox() is not None


def test_uppercase_preset_transforms(tmp_path, monkeypatch):
    from PIL import Image

    monkeypatch.setattr(textcard, "FONT_DIR", str(tmp_path / "nofonts"))
    lower, _ = textcard.render_text_card(
        "hi", str(tmp_path / "l.png"), 400, style=textcard.CardStyle()
    )
    upper, _ = textcard.render_text_card(
        "hi", str(tmp_path / "u.png"), 400,
        style=textcard.CardStyle(uppercase=True),
    )
    # uppercase glyphs are taller/wider -> different bounding box
    assert Image.open(lower).getbbox() != Image.open(upper).getbbox()


def test_install_fonts_downloads_and_skips(tmp_path, monkeypatch):
    monkeypatch.setattr(textcard, "FONT_DIR", str(tmp_path))

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "raw.githubusercontent.com"
        return httpx.Response(200, content=b"F" * 20_000)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    first = dict(install_fonts(client=client))
    assert set(first.values()) == {"installed"}
    second = dict(install_fonts(client=client))
    assert set(second.values()) == {"present"}


def test_install_fonts_reports_failures_without_raising(tmp_path, monkeypatch):
    monkeypatch.setattr(textcard, "FONT_DIR", str(tmp_path))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    results = dict(install_fonts(client=httpx.Client(
        transport=httpx.MockTransport(handler))))
    assert all(v.startswith("failed:") for v in results.values())
    assert not list(tmp_path.iterdir())  # nothing half-written


def test_tiny_response_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(textcard, "FONT_DIR", str(tmp_path))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>error page</html>")

    results = dict(install_fonts(client=httpx.Client(
        transport=httpx.MockTransport(handler))))
    assert all("suspiciously small" in v for v in results.values())
