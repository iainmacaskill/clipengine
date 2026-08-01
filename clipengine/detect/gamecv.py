"""Game-event detection via template matching (killfeeds, victory screens).

A *game profile* is a directory containing small grayscale reference images
(e.g. a victory banner crop) and a ``manifest.json`` describing where each
appears on screen and how strong a match must be:

    {
      "game": "league-of-legends",
      "capture_width": 960,
      "events": [
        {"name": "victory", "template": "victory.png",
         "region": [0.30, 0.25, 0.40, 0.25], "threshold": 0.70, "min_gap_s": 30}
      ]
    }

``region`` is fractional [x, y, w, h] of the frame; templates are captured at
``capture_width`` scale (crop a stream frame scaled to that width). Detection
streams frames at low fps, computes normalized cross-correlation of each
template over its region (FFT + integral images - no OpenCV), and emits both
discrete hits and a per-second SignalSeries for the fusion stage.
"""
from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np

from ..models import SignalSeries


@dataclass
class EventTemplate:
    name: str
    template: np.ndarray          # grayscale float array
    region: tuple[float, float, float, float]  # fractional x, y, w, h
    threshold: float
    min_gap_s: float


@dataclass
class GameProfile:
    game: str
    capture_width: int
    events: list[EventTemplate]


@dataclass
class EventHit:
    at: float
    name: str
    score: float


def _png_gray(path: str) -> np.ndarray:
    """Decode an image to a grayscale float array using ffmpeg (no PIL/cv2)."""
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", path],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    w, h = (int(v) for v in probe.split(","))
    raw = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", path,
         "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        check=True, capture_output=True,
    ).stdout
    return np.frombuffer(raw[: w * h], dtype=np.uint8).reshape(h, w).astype(np.float64)


def load_profile(profile_dir: str) -> GameProfile:
    manifest_path = os.path.join(profile_dir, "manifest.json")
    with open(manifest_path) as f:
        manifest = json.load(f)
    events = []
    for e in manifest.get("events", []):
        region = tuple(float(v) for v in e["region"])
        if len(region) != 4 or not all(0.0 <= v <= 1.0 for v in region):
            raise ValueError(f"event {e.get('name')}: region must be fractional [x,y,w,h]")
        template_path = os.path.join(profile_dir, e["template"])
        if not os.path.exists(template_path):
            raise FileNotFoundError(f"event {e.get('name')}: missing template {template_path}")
        events.append(
            EventTemplate(
                name=e["name"],
                template=_png_gray(template_path),
                region=region,  # type: ignore[arg-type]
                threshold=float(e.get("threshold", 0.7)),
                min_gap_s=float(e.get("min_gap_s", 30.0)),
            )
        )
    if not events:
        raise ValueError(f"game profile {profile_dir} defines no events")
    return GameProfile(
        game=manifest.get("game", os.path.basename(profile_dir)),
        capture_width=int(manifest.get("capture_width", 960)),
        events=events,
    )


def ncc_max(region: np.ndarray, template: np.ndarray) -> float:
    """Peak normalized cross-correlation of template over region, in [-1, 1].

    FFT cross-correlation for the numerator; integral images for the local
    sums in the denominator. Pure numpy.
    """
    rh, rw = region.shape
    th, tw = template.shape
    if th > rh or tw > rw:
        return -1.0
    t = template - template.mean()
    t_norm = float(np.sqrt((t**2).sum()))
    if t_norm < 1e-9:
        return -1.0

    # numerator: correlation of region with zero-mean template
    fshape = (rh + th - 1, rw + tw - 1)
    fr = np.fft.rfft2(region, fshape)
    ft = np.fft.rfft2(t[::-1, ::-1], fshape)
    corr = np.fft.irfft2(fr * ft, fshape)[th - 1 : rh, tw - 1 : rw]

    # local sums of region windows via integral images
    ii = np.cumsum(np.cumsum(np.pad(region, ((1, 0), (1, 0))), axis=0), axis=1)
    ii2 = np.cumsum(np.cumsum(np.pad(region**2, ((1, 0), (1, 0))), axis=0), axis=1)
    oh, ow = rh - th + 1, rw - tw + 1

    def _window_sums(integral):
        return (
            integral[th : th + oh, tw : tw + ow]
            - integral[:oh, tw : tw + ow]
            - integral[th : th + oh, :ow]
            + integral[:oh, :ow]
        )

    n = th * tw
    win_sum = _window_sums(ii)
    win_var = _window_sums(ii2) - win_sum**2 / n
    win_norm = np.sqrt(np.maximum(win_var, 1e-9))
    ncc = corr / (win_norm * t_norm)
    return float(ncc.max())


def iter_gray_frames(
    video_path: str, width: int, height: int, fps: float = 1.0
) -> Iterator[np.ndarray]:
    """Stream grayscale frames at low fps without loading the whole video."""
    proc = subprocess.Popen(
        [
            "ffmpeg", "-loglevel", "error", "-i", video_path,
            "-vf", f"fps={fps},scale={width}:{height}",
            "-pix_fmt", "gray", "-f", "rawvideo", "-",
        ],
        stdout=subprocess.PIPE,
    )
    frame_size = width * height
    try:
        assert proc.stdout is not None
        while True:
            raw = proc.stdout.read(frame_size)
            if len(raw) < frame_size:
                break
            yield np.frombuffer(raw, dtype=np.uint8).reshape(height, width).astype(np.float64)
    finally:
        proc.stdout.close()  # type: ignore[union-attr]
        proc.wait()


def score_frames(
    frames, profile: GameProfile, fps: float, duration: float
) -> tuple[SignalSeries, list[EventHit]]:
    """Match every template against its region per frame -> (series, hits).

    The series holds each second's best match score (0 floor) for fusion; hits
    are threshold crossings deduplicated by each event's min_gap_s.
    """
    scores = [0.0] * (int(duration) + 1)
    hits: list[EventHit] = []
    last_hit: dict[str, float] = {}
    for idx, frame in enumerate(frames):
        t = idx / fps
        h, w = frame.shape
        for event in profile.events:
            fx, fy, fw, fh = event.region
            region = frame[
                int(fy * h) : int((fy + fh) * h), int(fx * w) : int((fx + fw) * w)
            ]
            score = ncc_max(region, event.template)
            second = min(int(t), len(scores) - 1)
            scores[second] = max(scores[second], max(score, 0.0))
            if score >= event.threshold:
                if event.name in last_hit and t - last_hit[event.name] < event.min_gap_s:
                    continue
                last_hit[event.name] = t
                hits.append(EventHit(at=t, name=event.name, score=score))
    return SignalSeries("game_events", scores), hits


def detect_events(
    video_path: str, profile_dir: str, duration: float, fps: float = 1.0
) -> tuple[SignalSeries, list[EventHit]]:
    """Run a game profile over a video -> (fusion series, event hits)."""
    profile = load_profile(profile_dir)
    # preserve 16:9-ish aspect; height derived from capture width
    height = int(round(profile.capture_width * 9 / 16 / 2) * 2)
    frames = iter_gray_frames(video_path, profile.capture_width, height, fps=fps)
    return score_frames(frames, profile, fps, duration)
