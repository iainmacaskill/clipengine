"""Clipper-style text cards: styled hook/CTA overlays rendered with Pillow.

Draft 2 of on-screen text, built from what top clip pages actually use
(docs/caption-playbook.md): heavy bold font, white fill with a thick black
outline and soft shadow, short stacked lines, one highlighted keyword, and
real colour emoji — none of which ffmpeg's drawtext can do (it renders emoji
as empty boxes). The card is a transparent PNG that ffmpeg overlays.

Markup: wrap a word in *asterisks* to render it in the highlight colour.
Fonts are auto-discovered (macOS + Linux candidates) and overridable via
CLIPENGINE_FONT_FILE / CLIPENGINE_EMOJI_FONT. Without Pillow the pipeline
falls back to the plain drawtext style.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

BOLD_FONT_CANDIDATES = (
    # operator-installed clipper classics first
    "~/Library/Fonts/Montserrat-ExtraBold.ttf",
    "~/Library/Fonts/Montserrat-Black.ttf",
    "/usr/share/fonts/truetype/montserrat/Montserrat-ExtraBold.ttf",
    # stock heavy fonts
    "/System/Library/Fonts/Supplemental/Arial Black.ttf",
    "/Library/Fonts/Arial Black.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
)
EMOJI_FONT_CANDIDATES = (
    "/System/Library/Fonts/Apple Color Emoji.ttc",
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
    "~/Library/Fonts/NotoColorEmoji.ttf",
)
# CBDT/sbix emoji fonts only open at fixed strike sizes - probe the known ones
_EMOJI_STRIKES = (160, 137, 136, 128, 109, 96, 64, 32)

_EMOJI_RE = re.compile(
    "["
    "\U0001f000-\U0001faff"
    "\U0001f1e6-\U0001f1ff"
    "☀-➿"
    "⬀-⯿"
    "️"
    "]+"
)
_HILITE_RE = re.compile(r"\*([^*]+)\*")


FONT_DIR = os.path.expanduser("~/.clipengine/fonts")


@dataclass
class CardStyle:
    font_size: int = 76
    fill: str = "white"
    stroke: str = "black"
    stroke_frac: float = 0.11        # stroke width as a fraction of font size
    shadow: tuple = (4, 6, 140)      # dx, dy, alpha
    highlight: str = "#FFD400"       # clipper yellow for *marked* words
    line_spacing: float = 1.18
    max_line_chars: int = 16         # short stacked lines, readable at scroll speed
    uppercase: bool = False
    font_candidates: tuple = ()      # preset-specific fonts, tried before globals
    variation: str = ""              # variable-font named instance (e.g. ExtraBold)


# named looks from the research (docs/caption-playbook.md): distinct fonts +
# accent colours used by successful clip pages. Fonts are free/OFL, installed
# by 'clipengine fonts install' into ~/.clipengine/fonts.
PRESETS: dict[str, CardStyle] = {
    # the standard clipper look - Montserrat ExtraBold, yellow keyword
    "clean": CardStyle(
        font_candidates=("Montserrat[wght].ttf", "Montserrat-ExtraBold.ttf"),
        variation="ExtraBold", highlight="#FFD400",
    ),
    # Hormozi bold: Anton, ALL CAPS, saturated yellow keyword
    "hormozi": CardStyle(
        font_candidates=("Anton-Regular.ttf",), uppercase=True,
        highlight="#FFD93D", stroke_frac=0.12,
    ),
    # Hormozi's green alternate - electric green reads as money/positive
    "hormozi-green": CardStyle(
        font_candidates=("Anton-Regular.ttf",), uppercase=True,
        highlight="#A6FF00", stroke_frac=0.12,
    ),
    # comic energy (MrBeast-adjacent; Komika Axis isn't OFL, Bangers is)
    "beast": CardStyle(
        font_candidates=("Bangers-Regular.ttf",),
        highlight="#FF3131", stroke_frac=0.14, font_size=82,
    ),
    # heavy block statement - Archivo Black, urgency red keyword
    "block": CardStyle(
        font_candidates=("ArchivoBlack-Regular.ttf",),
        highlight="#FF3131",
    ),
    # rounded playful - Luckiest Guy, hot pink keyword
    "playful": CardStyle(
        font_candidates=("LuckiestGuy-Regular.ttf",),
        highlight="#FF5CA8", stroke_frac=0.13,
    ),
}


def get_preset(name: str) -> CardStyle:
    try:
        from dataclasses import replace

        return replace(PRESETS[name])
    except KeyError:
        raise ValueError(
            f"unknown style '{name}' - available: {', '.join(sorted(PRESETS))}"
        ) from None


# freely-licensed fonts (OFL/Apache) fetched straight from the google/fonts repo
FONT_SOURCES = {
    "Montserrat[wght].ttf":
        "https://raw.githubusercontent.com/google/fonts/main/ofl/montserrat/Montserrat%5Bwght%5D.ttf",
    "Anton-Regular.ttf":
        "https://raw.githubusercontent.com/google/fonts/main/ofl/anton/Anton-Regular.ttf",
    "Bangers-Regular.ttf":
        "https://raw.githubusercontent.com/google/fonts/main/ofl/bangers/Bangers-Regular.ttf",
    "ArchivoBlack-Regular.ttf":
        "https://raw.githubusercontent.com/google/fonts/main/ofl/archivoblack/ArchivoBlack-Regular.ttf",
    "LuckiestGuy-Regular.ttf":
        "https://raw.githubusercontent.com/google/fonts/main/apache/luckiestguy/LuckiestGuy-Regular.ttf",
}


def install_fonts(client=None) -> list[tuple[str, str]]:
    """Download the preset fonts into ~/.clipengine/fonts (skip existing).

    Returns (filename, status) pairs; status is 'installed', 'present', or an
    error string. A failed download never raises - the presets fall back to
    system fonts.
    """
    import httpx

    os.makedirs(FONT_DIR, exist_ok=True)
    client = client or httpx.Client(timeout=60.0, follow_redirects=True)
    results = []
    for name, url in FONT_SOURCES.items():
        dest = os.path.join(FONT_DIR, name)
        if os.path.exists(dest):
            results.append((name, "present"))
            continue
        try:
            resp = client.get(url)
            resp.raise_for_status()
            if len(resp.content) < 10_000:
                raise ValueError(f"suspiciously small ({len(resp.content)} bytes)")
            with open(dest, "wb") as f:
                f.write(resp.content)
            results.append((name, "installed"))
        except Exception as e:  # noqa: BLE001 - report, don't abort the rest
            results.append((name, f"failed: {str(e)[:80]}"))
    return results


def preset_status() -> list[tuple[str, str]]:
    """(preset, resolved font path or 'missing - system fallback') pairs."""
    rows = []
    for name, style in PRESETS.items():
        path = next(
            (p for c in style.font_candidates
             if os.path.exists(p := os.path.join(FONT_DIR, c))),
            None,
        )
        rows.append((name, path or f"missing -> fallback {find_bold_font() or 'NONE'}"))
    return rows


def available() -> bool:
    try:
        import PIL  # noqa: F401
        return True
    except ImportError:
        return False


def _find(candidates, env_var) -> str | None:
    override = os.environ.get(env_var)
    paths = ([override] if override else []) + [os.path.expanduser(c) for c in candidates]
    return next((p for p in paths if p and os.path.exists(p)), None)


def find_bold_font() -> str | None:
    return _find(BOLD_FONT_CANDIDATES, "CLIPENGINE_FONT_FILE")


def find_emoji_font() -> str | None:
    return _find(EMOJI_FONT_CANDIDATES, "CLIPENGINE_EMOJI_FONT")


def split_lines(text: str, max_chars: int) -> list[str]:
    """Stack the text into short centred lines; explicit newlines win."""
    lines: list[str] = []
    for raw in text.splitlines():
        words, current = raw.split(), ""
        for word in words:
            if current and len(current) + 1 + len(word) > max_chars:
                lines.append(current)
                current = word
            else:
                current = f"{current} {word}".strip()
        if current:
            lines.append(current)
    return lines or [text.strip()]


def _tokens(line: str):
    """(kind, text, highlighted) runs: kind is 'text' or 'emoji'."""
    for hl_part, highlighted in _split_highlight(line):
        pos = 0
        for m in _EMOJI_RE.finditer(hl_part):
            if m.start() > pos:
                yield "text", hl_part[pos:m.start()], highlighted
            yield "emoji", m.group(0), highlighted
            pos = m.end()
        if pos < len(hl_part):
            yield "text", hl_part[pos:], highlighted


def _split_highlight(line: str):
    pos = 0
    for m in _HILITE_RE.finditer(line):
        if m.start() > pos:
            yield line[pos:m.start()], False
        yield m.group(1), True
        pos = m.end()
    if pos < len(line):
        yield line[pos:], False


def _emoji_image(cluster: str, target: int):
    """Render an emoji run at a native strike size, scaled to the line."""
    from PIL import Image, ImageDraw, ImageFont

    path = find_emoji_font()
    if not path:
        return None
    for strike in _EMOJI_STRIKES:
        try:
            font = ImageFont.truetype(path, strike)
            canvas = Image.new("RGBA", (strike * (len(cluster) + 1), int(strike * 1.4)),
                               (0, 0, 0, 0))
            ImageDraw.Draw(canvas).text((0, 0), cluster, font=font, embedded_color=True)
            box = canvas.getbbox()
            if not box:
                return None
            glyph = canvas.crop(box)
            scale = target / glyph.height
            return glyph.resize((max(1, int(glyph.width * scale)), target))
        except OSError:
            continue
    return None


def render_text_card(text: str, out_png: str, width: int, style: CardStyle | None = None):
    """Render the card -> (png_path, height). Emoji without a usable emoji
    font are dropped from the card (they stay in captions), never crash."""
    from PIL import Image, ImageDraw, ImageFont

    style = style or CardStyle()
    font_path = next(
        (p for c in style.font_candidates
         if os.path.exists(p := os.path.join(FONT_DIR, c))),
        None,
    ) or find_bold_font()
    if font_path is None:
        raise RuntimeError(
            "no bold font found - run 'clipengine fonts install', or set "
            "CLIPENGINE_FONT_FILE to a .ttf (Montserrat ExtraBold recommended)"
        )
    font = ImageFont.truetype(font_path, style.font_size)
    if style.variation:
        try:
            font.set_variation_by_name(style.variation)
        except Exception:  # static font / instance not present - use as loaded
            pass
    if style.uppercase:
        text = text.upper()
    stroke_w = max(2, int(style.font_size * style.stroke_frac))
    line_h = int(style.font_size * style.line_spacing)
    emoji_h = int(style.font_size * 1.05)

    lines = split_lines(text, style.max_line_chars)
    height = line_h * len(lines) + stroke_w * 2 + style.shadow[1] + 8
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    for i, line in enumerate(lines):
        runs = []
        for kind, run, hl in _tokens(line):
            if kind == "emoji":
                glyph = _emoji_image(run, emoji_h)
                if glyph is not None:
                    runs.append(("emoji", glyph, hl))
            elif run.strip() or runs:
                runs.append(("text", run, hl))
        if not runs:
            continue
        total = sum(
            run.width if kind == "emoji" else draw.textlength(run, font=font)
            for kind, run, _hl in runs
        )
        x = max(0, (width - int(total)) // 2)
        y = i * line_h + stroke_w
        for kind, run, hl in runs:
            if kind == "emoji":
                img.alpha_composite(run, (int(x), y + (style.font_size - emoji_h) // 2))
                x += run.width
                continue
            dx, dy, alpha = style.shadow
            draw.text((x + dx, y + dy), run, font=font,
                      fill=(0, 0, 0, alpha), stroke_width=stroke_w,
                      stroke_fill=(0, 0, 0, alpha))
            draw.text((x, y), run, font=font,
                      fill=style.highlight if hl else style.fill,
                      stroke_width=stroke_w, stroke_fill=style.stroke)
            x += draw.textlength(run, font=font)

    img.save(out_png)
    return out_png, height
