"""Edit stage: frame-accurate trims and 16:9 -> 9:16 vertical reformatting.

Layout: facecam tile on top, gameplay centre-crop below - the dominant meta for
gaming shorts. Ported from the validated spike run (see docs/spike-notes.md).
"""
from __future__ import annotations

import json
import subprocess

from ..config import EditConfig
from ..models import FacecamRegion, SourceVideo


def probe(path: str) -> SourceVideo:
    import os

    if not os.path.exists(path):
        raise ValueError(f"video file not found: {path}")
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height", "-show_entries", "format=duration",
                "-of", "json", path,
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except subprocess.CalledProcessError as e:
        raise ValueError(
            f"cannot read {path} as video ({(e.stderr or '').strip()[:200] or 'ffprobe failed'})"
            " - is it a complete, valid video file?"
        ) from e
    data = json.loads(out)
    stream = data["streams"][0]
    return SourceVideo(
        path=path,
        width=int(stream["width"]),
        height=int(stream["height"]),
        duration=float(data["format"]["duration"]),
    )


def trim(src: str, dst: str, start: float, duration: float, cfg: EditConfig) -> str:
    """Frame-accurate trim (re-encode; stream-copy would snap to keyframes)."""
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", src,
            "-c:v", "libx264", "-preset", cfg.preset, "-crf", str(cfg.crf),
            "-c:a", "aac", dst,
        ],
        check=True,
    )
    return dst


def escape_drawtext(text: str) -> str:
    """Escape a string for ffmpeg drawtext, assuming the call site wraps the
    result in single quotes (text='...').

    Backslash/colon/percent are drawtext-level escapes; an apostrophe needs
    the quote-break form ('\\'') because backslash-escaping does not work
    inside a quoted filter argument - a hook like "you're" aborts the render
    otherwise (found by the Fightland batch proof-run).
    """
    out = text.replace("\\", "\\\\")
    for ch in (":", "%"):
        out = out.replace(ch, "\\" + ch)
    return out.replace("'", "'\\''")


def vertical_graph(
    source: SourceVideo,
    facecam: FacecamRegion,
    cfg: EditConfig,
    credit_text: str | None = None,
) -> str:
    """Build the 16:9 -> 9:16 filtergraph; optionally burn a credit line into the
    seam just below the facecam tile (clear of the face and of bottom captions)."""
    cam_h = cfg.facecam_tile_height
    game_h = cfg.out_height - cam_h
    # gameplay crop with the bottom tile's aspect ratio, full source height
    crop_w = min(source.width, round(source.height * cfg.out_width / game_h))
    crop_x = (source.width - crop_w) // 2
    graph = (
        f"[0:v]split=2[c][g];"
        f"[c]crop={facecam.w}:{facecam.h}:{facecam.x}:{facecam.y},"
        f"scale={cfg.out_width}:{cam_h}:flags=lanczos[cam];"
        f"[g]crop={crop_w}:{source.height}:{crop_x}:0,"
        f"scale={cfg.out_width}:{game_h}:flags=lanczos[game];"
        f"[cam][game]vstack[v]"
    )
    if credit_text:
        graph += (
            f";[v]drawtext=text='{escape_drawtext(credit_text)}'"
            f":font=Sans:fontsize={cfg.credit_font_size}"
            f":fontcolor=white@0.9:borderw=3:bordercolor=black@0.9"
            f":x=(w-tw)/2:y={cam_h + 14}[v]"
        )
    return graph


def vertical_fit_graph(
    source: SourceVideo,
    cfg: EditConfig,
    credit_text: str | None = None,
    cta_text: str | None = None,
) -> str:
    """Fit-to-9:16 filtergraph for repurposed asset footage (no facecam):
    the source scaled to fit, centred over a blurred fill of itself. Optional
    credit line at the top edge and CTA line above the caption zone."""
    w, h = cfg.out_width, cfg.out_height
    graph = (
        f"[0:v]split=2[bg][fg];"
        f"[bg]scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h},boxblur=24:6[bgb];"
        f"[fg]scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos[fgs];"
        f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2[v]"
    )
    if credit_text:
        graph += (
            f";[v]drawtext=text='{escape_drawtext(credit_text)}'"
            f":font=Sans:fontsize={cfg.credit_font_size}"
            f":fontcolor=white@0.9:borderw=3:bordercolor=black@0.9"
            f":x=(w-tw)/2:y=60[v]"
        )
    if cta_text:
        graph += (
            f";[v]drawtext=text='{escape_drawtext(cta_text)}'"
            f":font=Sans:fontsize={cfg.credit_font_size + 6}"
            f":fontcolor=white:borderw=4:bordercolor=black"
            f":x=(w-tw)/2:y=h-380[v]"
        )
    return graph


def vertical_fit(
    src: str,
    dst: str,
    source: SourceVideo,
    cfg: EditConfig,
    credit_text: str | None = None,
    cta_text: str | None = None,
) -> str:
    """Reformat any aspect ratio to 9:16 with a blurred self-fill (no facecam)."""
    graph = vertical_fit_graph(source, cfg, credit_text=credit_text, cta_text=cta_text)
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error", "-i", src,
            "-filter_complex", graph, "-map", "[v]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", cfg.preset, "-crf", str(cfg.crf),
            "-pix_fmt", "yuv420p", "-c:a", "aac", dst,
        ],
        check=True,
    )
    return dst


def vertical(
    src: str,
    dst: str,
    source: SourceVideo,
    facecam: FacecamRegion,
    cfg: EditConfig,
    credit_text: str | None = None,
) -> str:
    """Reformat 16:9 -> 9:16: facecam scaled into the top tile, gameplay centre-crop below."""
    graph = vertical_graph(source, facecam, cfg, credit_text=credit_text)
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error", "-i", src,
            "-filter_complex", graph, "-map", "[v]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", cfg.preset, "-crf", str(cfg.crf),
            "-pix_fmt", "yuv420p", "-c:a", "aac", dst,
        ],
        check=True,
    )
    return dst


def overlay_cards(
    src: str,
    dst: str,
    cards: list[tuple[str, float, float | None]],
    cfg: EditConfig,
) -> str:
    """Overlay rendered text-card PNGs in one pass.

    Each card is (png_path, y_fraction_of_height, seconds_or_None): centred
    horizontally, positioned at y = fraction * H, shown for the first N
    seconds or persistently when None.
    """
    inputs: list[str] = ["-i", src]
    chains = []
    prev = "0:v"
    for i, (png, y_frac, seconds) in enumerate(cards, start=1):
        inputs += ["-i", png]
        enable = f":enable='lt(t,{seconds})'" if seconds else ""
        label = "v" if i == len(cards) else f"s{i}"
        chains.append(
            f"[{prev}][{i}:v]overlay=(W-w)/2:{y_frac:.3f}*H{enable}[{label}]"
        )
        prev = label
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error", *inputs,
            "-filter_complex", ";".join(chains), "-map", "[v]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", cfg.preset, "-crf", str(cfg.crf),
            "-pix_fmt", "yuv420p", "-c:a", "copy", dst,
        ],
        check=True,
    )
    return dst


def burn_hook(src: str, dst: str, hook_text: str, cfg: EditConfig) -> str:
    """Burn a large text hook over the first 2.5 seconds of a vertical clip."""
    y = cfg.facecam_tile_height + 70
    vf = (
        f"drawtext=text='{escape_drawtext(hook_text)}'"
        f":font=Sans:fontsize=64:fontcolor=white"
        f":borderw=5:bordercolor=black"
        f":x=(w-tw)/2:y={y}:enable='lt(t,2.5)'"
    )
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error", "-i", src,
            "-vf", vf,
            "-c:v", "libx264", "-preset", cfg.preset, "-crf", str(cfg.crf),
            "-c:a", "copy", dst,
        ],
        check=True,
    )
    return dst


def burn_subtitles(src: str, dst: str, ass_path: str, cfg: EditConfig) -> str:
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error", "-i", src,
            "-vf", f"subtitles={ass_path}",
            "-c:v", "libx264", "-preset", cfg.preset, "-crf", str(cfg.crf),
            "-c:a", "copy", dst,
        ],
        check=True,
    )
    return dst
