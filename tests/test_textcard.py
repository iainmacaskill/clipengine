import pytest

from clipengine.edit.textcard import (
    CardStyle,
    _tokens,
    available,
    find_bold_font,
    render_text_card,
    split_lines,
)

pytestmark = pytest.mark.skipif(not available(), reason="Pillow not installed")


# -- line stacking ---------------------------------------------------------


def test_split_lines_stacks_short_lines():
    lines = split_lines("this AI builds Roblox GUIs in seconds", 16)
    assert lines == ["this AI builds", "Roblox GUIs in", "seconds"]
    assert all(len(ln) <= 16 for ln in lines)


def test_split_lines_respects_explicit_newlines():
    assert split_lines("TOP LINE\nbottom line", 30) == ["TOP LINE", "bottom line"]


def test_split_lines_never_returns_empty():
    assert split_lines("word", 16) == ["word"]


# -- token runs ------------------------------------------------------------


def test_tokens_separate_emoji_and_highlight():
    runs = list(_tokens("new *series* alert 🚨"))
    kinds = [(k, hl) for k, _t, hl in runs]
    assert ("emoji", False) in kinds
    assert ("text", True) in kinds        # *series* highlighted
    texts = [t for k, t, _ in runs if k == "text"]
    assert any("series" in t for t in texts)


# -- rendering -------------------------------------------------------------


def test_render_card_produces_transparent_png(tmp_path):
    from PIL import Image

    path, height = render_text_card(
        "new *series* alert", str(tmp_path / "card.png"), 980
    )
    img = Image.open(path)
    assert img.mode == "RGBA" and img.width == 980 and img.height == height
    # transparent background, opaque text somewhere
    corner = img.getpixel((2, 2))
    assert corner[3] == 0
    assert img.getbbox() is not None


def test_render_card_highlight_uses_yellow(tmp_path):
    from PIL import Image

    plain, _ = render_text_card("ALERT", str(tmp_path / "p.png"), 600)
    hl, _ = render_text_card("*ALERT*", str(tmp_path / "h.png"), 600)
    def has_yellowish(img):
        for px in img.convert("RGBA").getdata():
            if px[3] > 200 and px[0] > 200 and px[1] > 150 and px[2] < 100:
                return True
        return False
    assert not has_yellowish(Image.open(plain))
    assert has_yellowish(Image.open(hl))


def test_render_card_with_emoji_never_crashes(tmp_path):
    # emoji renders in colour when an emoji font exists, is dropped otherwise
    path, _ = render_text_card("alert 🚨", str(tmp_path / "e.png"), 600)
    from PIL import Image

    assert Image.open(path).getbbox() is not None


def test_render_card_multiline_height_scales(tmp_path):
    _p1, h1 = render_text_card("short", str(tmp_path / "1.png"), 900)
    _p2, h2 = render_text_card(
        "a much longer hook that stacks into several lines", str(tmp_path / "2.png"), 900
    )
    assert h2 > h1


def test_missing_bold_font_raises_helpful_error(tmp_path, monkeypatch):
    import clipengine.edit.textcard as tc

    monkeypatch.setattr(tc, "find_bold_font", lambda: None)
    with pytest.raises(RuntimeError, match="CLIPENGINE_FONT_FILE"):
        tc.render_text_card("x", str(tmp_path / "x.png"), 400)


def test_bold_font_discovered_in_environment():
    assert find_bold_font() is not None  # sandbox has DejaVu/Liberation bold
