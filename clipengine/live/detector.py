"""Live chat spike detection.

Maintains a rolling baseline of chat message rate and triggers when the
short-window rate spikes far above it - the live-mode equivalent of the offline
detector's chat-velocity signal. Pure logic over message timestamps (no clock
access), so it is deterministic and unit-testable.
"""
from __future__ import annotations

from bisect import bisect_left
from collections import deque
from dataclasses import dataclass


@dataclass
class Spike:
    at: float          # timestamp of the triggering message
    rate: float        # messages/sec over the short window
    baseline: float    # baseline mean rate
    z: float           # how many baseline std-devs above the mean


class SpikeDetector:
    def __init__(
        self,
        baseline_s: float = 300.0,
        window_s: float = 10.0,
        z_threshold: float = 3.0,
        min_rate: float = 1.0,
        cooldown_s: float = 120.0,
        min_baseline_s: float = 60.0,
    ):
        self.baseline_s = baseline_s
        self.window_s = window_s
        self.z_threshold = z_threshold
        self.min_rate = min_rate
        self.cooldown_s = cooldown_s
        self.min_baseline_s = min_baseline_s
        self._times: deque[float] = deque()
        self._started_at: float | None = None
        self._last_spike_at: float | None = None

    def add(self, t: float) -> Spike | None:
        """Register a chat message at time ``t``; returns a Spike when triggered."""
        if self._started_at is None:
            self._started_at = t
        self._times.append(t)
        while self._times and self._times[0] < t - self.baseline_s:
            self._times.popleft()

        # warm-up: no triggering until a baseline exists
        if t - self._started_at < self.min_baseline_s:
            return None
        if self._last_spike_at is not None and t - self._last_spike_at < self.cooldown_s:
            return None

        times = list(self._times)
        split = bisect_left(times, t - self.window_s)
        recent, past = times[split:], times[:split]
        rate = len(recent) / self.window_s
        if rate < self.min_rate or not past:
            return None

        # baseline: rates of consecutive window_s bins over the older span
        span = past[-1] - past[0]
        n_bins = max(int(span / self.window_s), 1)
        bins = [0] * n_bins
        for pt in past:
            idx = min(int((pt - past[0]) / self.window_s), n_bins - 1)
            bins[idx] += 1
        rates = [b / self.window_s for b in bins]
        mean = sum(rates) / len(rates)
        var = sum((r - mean) ** 2 for r in rates) / len(rates)
        std = max(var**0.5, 0.1)  # floor: quiet chats would otherwise trigger on noise

        z = (rate - mean) / std
        if z < self.z_threshold:
            return None
        self._last_spike_at = t
        return Spike(at=t, rate=rate, baseline=mean, z=z)
