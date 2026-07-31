"""Detector evaluation and weight tuning.

Ground truth = the moments viewers themselves clipped (Twitch clip vod_offsets,
fetched via ``clipengine truth``). The tuner grid-searches signal-weight
combinations, re-running only the cheap fusion step over precomputed signal
series, and ranks configurations by how well their top windows cover the
top viewer-clipped moments.

Metric: recall@N - the fraction of the top-M truth moments that fall inside any
of the detector's top-N candidate windows. Secondary ordering prefers configs
whose hits sit higher in the candidate ranking.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, replace

from ..config import DetectConfig
from ..models import ClipCandidate, SignalSeries
from . import fusion

_GRID_VALUES = (0.0, 0.25, 0.5, 1.0)
_SIGNALS = ("chat_velocity", "chat_emotes", "audio_energy")


@dataclass
class EvalResult:
    recall: float          # covered truth moments / considered truth moments
    hits: int
    n_truth: int
    mean_hit_rank: float   # avg candidate rank (0-based) of covering windows; lower is better


def evaluate(
    candidates: list[ClipCandidate],
    truth: list[dict],
    top_n: int | None = None,
    top_truth: int | None = None,
) -> EvalResult:
    """Score candidate windows against viewer-clipped truth moments.

    ``truth`` rows need an "offset" (seconds into the VOD); they are considered
    views-descending, truncated to ``top_truth``. A moment is covered if its
    offset lies inside a candidate window.
    """
    considered = truth[:top_truth] if top_truth else truth
    window = candidates[:top_n] if top_n else candidates
    hits = 0
    ranks = []
    for moment in considered:
        offset = float(moment["offset"])
        for rank, c in enumerate(window):
            if c.start <= offset <= c.end:
                hits += 1
                ranks.append(rank)
                break
    n = len(considered)
    return EvalResult(
        recall=hits / n if n else 0.0,
        hits=hits,
        n_truth=n,
        mean_hit_rank=sum(ranks) / len(ranks) if ranks else float("inf"),
    )


def weight_grid(
    signals: tuple[str, ...] = _SIGNALS, values: tuple[float, ...] = _GRID_VALUES
) -> list[dict[str, float]]:
    """All weight combinations over the grid, excluding the all-zero point."""
    combos = []
    for vals in itertools.product(values, repeat=len(signals)):
        if any(v > 0 for v in vals):
            combos.append(dict(zip(signals, vals)))
    return combos


def tune(
    series: list[SignalSeries],
    duration: float,
    truth: list[dict],
    cfg: DetectConfig,
    top_n: int | None = None,
    top_truth: int = 10,
    grid: list[dict[str, float]] | None = None,
) -> list[tuple[dict[str, float], EvalResult]]:
    """Rank weight configurations by recall against the truth moments.

    Signals are computed once by the caller; each grid point only re-runs fusion.
    Only weights for signals present in ``series`` are meaningful - grid points
    referencing absent signals still run (the weight just has nothing to act on).
    """
    available = {s.name for s in series}
    grid = grid or weight_grid(tuple(s for s in _SIGNALS if s in available))
    results = []
    for weights in grid:
        candidates = fusion.fuse(series, weights, duration, replace(cfg))
        results.append((weights, evaluate(candidates, truth, top_n=top_n, top_truth=top_truth)))
    results.sort(key=lambda r: (-r[1].recall, r[1].mean_hit_rank))
    return results


def to_config_toml(weights: dict[str, float]) -> str:
    """Render a winning weight set as a [detect] config snippet."""
    lines = ["[detect]"]
    for name, value in sorted(weights.items()):
        lines.append(f"weight_{name} = {value}")
    return "\n".join(lines) + "\n"
