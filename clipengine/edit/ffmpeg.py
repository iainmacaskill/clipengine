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


def vertical(
    src: str,
    dst: str,
    source: SourceVideo,
    facecam: FacecamRegion,
    cfg: EditConfig,
) -> str:
    """Reformat 16:9 -> 9:16: facecam scaled into the top tile, gameplay centre-crop below."""
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
