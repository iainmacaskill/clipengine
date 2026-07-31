"""Burned-caption generation: word-timestamped ASS subtitles.

Opus-style word-by-word highlight captions (approach validated in the spike via
the public clipify skill; reimplemented here for batch use).
"""
from __future__ import annotations

from ..config import CaptionConfig
from ..models import Transcript

_WHITE = "&H00FFFFFF&"
_OUTLINE = "&H00000000&"

_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{size},{white},&H000000FF,{outline},&H00000000,1,0,0,0,100,100,0,0,1,8,3,2,60,60,280,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _fmt_time(t: float) -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t - h * 3600 - m * 60
    return f"{h}:{m:02d}:{s:05.2f}"


def build_ass(
    transcript: Transcript,
    cfg: CaptionConfig,
    play_w: int = 1080,
    play_h: int = 1920,
) -> str:
    """Render an ASS subtitle document with per-word active-highlight events."""
    words = transcript.words()
    chunks = [words[i : i + cfg.chunk_words] for i in range(0, len(words), cfg.chunk_words)]

    events = []
    for chunk in chunks:
        chunk_end = chunk[-1].end
        for i, w in enumerate(chunk):
            seg_start = w.start
            seg_end = chunk[i + 1].start if i + 1 < len(chunk) else chunk_end
            if seg_end <= seg_start:
                seg_end = seg_start + 0.05
            parts = []
            for j, ww in enumerate(chunk):
                if j == i and cfg.highlight_colour:
                    parts.append(f"{{\\c{cfg.highlight_colour}}}{ww.text}{{\\c{_WHITE}}}")
                else:
                    parts.append(ww.text)
            line = " ".join(parts)
            events.append(
                f"Dialogue: 0,{_fmt_time(seg_start)},{_fmt_time(seg_end)},Default,,0,0,0,,{line}"
            )

    header = _HEADER.format(
        w=play_w, h=play_h, font=cfg.font, size=cfg.font_size, white=_WHITE, outline=_OUTLINE
    )
    return header + "\n".join(events) + "\n"


def write_ass(transcript: Transcript, path: str, cfg: CaptionConfig) -> str:
    with open(path, "w") as f:
        f.write(build_ass(transcript, cfg))
    return path
