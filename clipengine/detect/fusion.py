"""Fuse per-second signal series into ranked, non-overlapping clip candidates."""
from __future__ import annotations

import numpy as np

from ..config import DetectConfig
from ..models import ClipCandidate, SignalSeries


def _normalise(scores: list[float], length: int) -> np.ndarray:
    """Pad/trim to a common length and z-score (flat series normalise to zeros)."""
    arr = np.zeros(length)
    n = min(len(scores), length)
    arr[:n] = scores[:n]
    std = arr.std()
    if std < 1e-9:
        return np.zeros(length)
    return (arr - arr.mean()) / std


def fuse(
    series: list[SignalSeries],
    weights: dict[str, float],
    duration: float,
    cfg: DetectConfig,
) -> list[ClipCandidate]:
    """Combine signals and pick the top non-overlapping windows.

    1. z-score each series over the full timeline
    2. weighted sum -> fused per-second score
    3. sliding-window mean at the target clip duration
    4. greedy pick of top windows, enforcing `min_gap` spacing
    """
    length = int(duration) + 1
    normed = {s.name: _normalise(s.scores, length) for s in series}
    fused = np.zeros(length)
    for name, arr in normed.items():
        fused += weights.get(name, 1.0) * arr

    # clamp the scoring window to the source length so short sources still localise
    win = max(1, min(int(cfg.target_duration), length - 1))
    kernel = np.ones(win) / win
    window_scores = np.convolve(fused, kernel, mode="valid")

    order = np.argsort(window_scores)[::-1]
    picked: list[ClipCandidate] = []
    for idx in order:
        if len(picked) >= cfg.top_n:
            break
        start = max(0.0, float(idx) - cfg.pre_roll)
        end = min(duration, start + cfg.target_duration)
        if any(
            start < c.end + cfg.min_gap and end > c.start - cfg.min_gap for c in picked
        ):
            continue
        breakdown = {
            name: float(arr[int(start) : int(end) + 1].mean()) for name, arr in normed.items()
        }
        picked.append(
            ClipCandidate(
                start=start,
                end=end,
                score=float(window_scores[idx]),
                signal_breakdown=breakdown,
            )
        )
    picked.sort(key=lambda c: c.score, reverse=True)
    return picked
