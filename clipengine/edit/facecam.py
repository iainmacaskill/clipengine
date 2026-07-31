"""Facecam auto-detection.

A facecam overlay is an axis-aligned rectangle whose border stays fixed while
gameplay moves around it. We sample frames across the source, build temporal
edge-persistence maps (edges present at the same pixel in most frames), and pick
the rectangle whose perimeter is most persistently edged. Pure numpy + ffmpeg -
no OpenCV/model dependency; good enough for static stream layouts, which is the
overwhelmingly common case. Scene-switching layouts need per-segment re-detection.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass

import numpy as np

from ..models import FacecamRegion
from .ffmpeg import probe

# rectangle constraints, as fractions of the (downscaled) frame width/height
_MIN_W_FRAC, _MAX_W_FRAC = 0.10, 0.50
_MIN_H_FRAC, _MAX_H_FRAC = 0.10, 0.60
_MIN_ASPECT, _MAX_ASPECT = 0.9, 2.4  # w/h: webcams are ~square to ~16:9
_STABLE_PERCENTILE = 99.0   # binarisation threshold on the min-gradient map
_MIN_GRADIENT = 12.0        # absolute floor for a "stable edge" (0-255 units)
_TOP_K_LINES = 30           # candidate rows/columns per orientation
_MIN_SCORE = 0.35           # below this, report "no facecam found"


@dataclass
class FacecamDetection:
    region: FacecamRegion
    score: float


def extract_gray_frames(video_path: str, n_frames: int = 24, width: int = 480) -> np.ndarray:
    """Sample n grayscale frames evenly across the video -> array (n, H, W)."""
    src = probe(video_path)
    height = int(round(src.height * width / src.width / 2) * 2)
    fps = max(n_frames / max(src.duration, 1e-6), 1e-4)
    raw = subprocess.run(
        [
            "ffmpeg", "-loglevel", "error", "-i", video_path,
            "-vf", f"fps={fps},scale={width}:{height}",
            "-pix_fmt", "gray", "-f", "rawvideo", "-frames:v", str(n_frames), "-",
        ],
        check=True,
        capture_output=True,
    ).stdout
    frame_size = width * height
    n = len(raw) // frame_size
    if n == 0:
        raise RuntimeError(f"no frames decoded from {video_path}")
    arr = np.frombuffer(raw[: n * frame_size], dtype=np.uint8)
    return arr.reshape(n, height, width).astype(np.float32)


def edge_stability(frames: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per-pixel MINIMUM gradient magnitude across frames.

    A static border keeps a strong edge in every frame, so its min-gradient stays
    high; moving content (gameplay, even noise) eventually has a weak-gradient
    frame at any pixel, dragging its minimum down. Returns (sv, sh), both (H, W):
    sv from x-gradients (rectangle *sides*), sh from y-gradients (top/bottom).
    """
    n, h, w = frames.shape
    sv = np.full((h, w), np.inf, dtype=np.float32)
    sh = np.full((h, w), np.inf, dtype=np.float32)
    for f in frames:
        gx = np.zeros((h, w), dtype=np.float32)
        gy = np.zeros((h, w), dtype=np.float32)
        gx[:, 1:] = np.abs(np.diff(f, axis=1))
        gy[1:, :] = np.abs(np.diff(f, axis=0))
        sv = np.minimum(sv, gx)
        sh = np.minimum(sh, gy)
    return sv, sh


def find_facecam(frames: np.ndarray) -> FacecamDetection | None:
    """Locate the facecam rectangle in a downscaled grayscale frame stack."""
    h, w = frames.shape[1:]
    sv, sh = edge_stability(frames)
    thresh_v = max(float(np.percentile(sv, _STABLE_PERCENTILE)), _MIN_GRADIENT)
    thresh_h = max(float(np.percentile(sh, _STABLE_PERCENTILE)), _MIN_GRADIENT)
    pv_b = (sv >= thresh_v).astype(np.float32)
    ph_b = (sh >= thresh_h).astype(np.float32)

    col_mass = pv_b.sum(axis=0)
    row_mass = ph_b.sum(axis=1)
    cols = np.argsort(col_mass)[::-1][:_TOP_K_LINES]
    rows = np.argsort(row_mass)[::-1][:_TOP_K_LINES]
    cols = np.sort(cols[col_mass[cols] > 0])
    rows = np.sort(rows[row_mass[rows] > 0])

    candidates: list[FacecamDetection] = []
    for i, x0 in enumerate(cols):
        for x1 in cols[i + 1 :]:
            rw = x1 - x0
            if not (_MIN_W_FRAC * w <= rw <= _MAX_W_FRAC * w):
                continue
            for j, y0 in enumerate(rows):
                for y1 in rows[j + 1 :]:
                    rh = y1 - y0
                    if not (_MIN_H_FRAC * h <= rh <= _MAX_H_FRAC * h):
                        continue
                    aspect = rw / rh
                    if not (_MIN_ASPECT <= aspect <= _MAX_ASPECT):
                        continue
                    # perimeter persistence: sides from pv, top/bottom from ph
                    left = pv_b[y0:y1, x0].mean()
                    right = pv_b[y0:y1, x1].mean()
                    top = ph_b[y0, x0:x1].mean()
                    bottom = ph_b[y1, x0:x1].mean()
                    score = float((left + right + top + bottom) / 4)
                    if score >= _MIN_SCORE:
                        candidates.append(
                            FacecamDetection(
                                FacecamRegion(int(x0), int(y0), int(rw), int(rh)), score
                            )
                        )
    if not candidates:
        return None
    # the facecam is the OUTERMOST stable rectangle; inner UI details form smaller
    # stable rectangles too, so among near-best scores prefer the largest area
    best_score = max(c.score for c in candidates)
    contenders = [c for c in candidates if c.score >= 0.85 * best_score]
    return max(contenders, key=lambda c: c.region.w * c.region.h)


def detect_facecam(
    video_path: str, n_frames: int = 24, width: int = 480
) -> FacecamDetection | None:
    """Detect the facecam region of a video, in source pixel coordinates."""
    src = probe(video_path)
    frames = extract_gray_frames(video_path, n_frames=n_frames, width=width)
    found = find_facecam(frames)
    if found is None:
        return None
    scale = src.width / frames.shape[2]
    r = found.region
    return FacecamDetection(
        FacecamRegion(
            x=int(r.x * scale),
            y=int(r.y * scale),
            w=int(r.w * scale),
            h=int(r.h * scale),
        ),
        found.score,
    )
