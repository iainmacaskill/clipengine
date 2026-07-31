"""VOD video downloader (yt-dlp wrapper).

Requires the optional dependency: ``pip install 'clipengine[download]'``.

Routes, per the product plan: streamer-authorised downloads are the end state
(Model A/C opt-in grants); yt-dlp against the public VOD URL is the pragmatic
first implementation. Sub-only VODs need the streamer's cooperation (pass their
browser cookies via ``cookies_file``). Only ingest streamers on the permission
roster (product plan §2).
"""
from __future__ import annotations

import os
import re

_VOD_URL = "https://www.twitch.tv/videos/{id}"


def normalise_vod_url(vod: str) -> str:
    """Accept a bare VOD id ('2274633451') or any twitch VOD URL form."""
    vod = vod.strip()
    if re.fullmatch(r"\d+", vod):
        return _VOD_URL.format(id=vod)
    m = re.search(r"twitch\.tv/videos/(\d+)", vod)
    if m:
        return _VOD_URL.format(id=m.group(1))
    raise ValueError(f"not a Twitch VOD id or URL: {vod!r}")


def build_opts(
    dst_path: str,
    max_height: int = 1080,
    start: float | None = None,
    end: float | None = None,
    cookies_file: str | None = None,
) -> dict:
    """Build yt-dlp options. Pure function so tests can assert on it.

    - quality capped at ``max_height`` (1080p is plenty for 9:16 output; see plan)
    - optional [start, end) range download for spot-checks without a full-VOD pull
    """
    opts: dict = {
        "outtmpl": {"default": dst_path},
        "format": f"best[height<={max_height}]/bestvideo[height<={max_height}]+bestaudio/best",
        "noplaylist": True,
        "retries": 4,
        "concurrent_fragment_downloads": 4,
        "quiet": False,
        "no_warnings": True,
    }
    if cookies_file:
        opts["cookiefile"] = cookies_file
    if start is not None or end is not None:
        try:
            from yt_dlp.utils import download_range_func
        except ImportError as e:
            raise RuntimeError(
                "yt-dlp not installed - run: pip install 'clipengine[download]'"
            ) from e
        opts["download_ranges"] = download_range_func(
            [], [(start or 0.0, end if end is not None else float("inf"))]
        )
        # range cuts land on keyframes unless re-encoded at the cut points
        opts["force_keyframes_at_cuts"] = True
    return opts


def download_clip_url(url: str, dst_path: str) -> str:
    """Download a Twitch clip (or any yt-dlp-supported URL) to ``dst_path``.

    Used by live mode to fetch clips created via the Create Clip API.
    """
    try:
        from yt_dlp import YoutubeDL
    except ImportError as e:
        raise RuntimeError(
            "yt-dlp not installed - run: pip install 'clipengine[download]'"
        ) from e

    opts = build_opts(dst_path)
    with YoutubeDL(opts) as ydl:
        code = ydl.download([url])
    if code != 0 or not os.path.exists(dst_path):
        raise RuntimeError(f"clip download failed for {url}")
    return dst_path


def download_vod(
    vod: str,
    dst_path: str,
    max_height: int = 1080,
    start: float | None = None,
    end: float | None = None,
    cookies_file: str | None = None,
) -> str:
    """Download a VOD (or a [start, end) slice of it) to ``dst_path``."""
    try:
        from yt_dlp import YoutubeDL
    except ImportError as e:
        raise RuntimeError(
            "yt-dlp not installed - run: pip install 'clipengine[download]'"
        ) from e

    url = normalise_vod_url(vod)
    opts = build_opts(
        dst_path, max_height=max_height, start=start, end=end, cookies_file=cookies_file
    )
    with YoutubeDL(opts) as ydl:
        code = ydl.download([url])
    if code != 0 or not os.path.exists(dst_path):
        raise RuntimeError(f"VOD download failed for {url}")
    return dst_path
