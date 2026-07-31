"""Live-mode orchestrator: watch a stream's chat, capture clips on hype spikes.

Flow per spike: chat velocity spikes above the rolling baseline -> Twitch's
Create Clip API captures the preceding ~90s server-side -> the processed clip
is downloaded -> an event is appended to the session's events file. Rendering
and publishing then reuse the ordinary pipeline (`clipengine process` on the
downloaded clip, or manual render/queue).

The permission roster gates monitoring exactly like offline ingestion.
"""
from __future__ import annotations

import json
import os
from collections.abc import Iterator
from dataclasses import dataclass

from ..config import Config
from .detector import Spike, SpikeDetector


@dataclass
class LiveEvent:
    at: float
    rate: float
    z: float
    clip_id: str | None = None      # None in dry-run mode
    clip_path: str | None = None    # None if capture/download failed
    error: str | None = None


def default_capture(cfg: Config, streamer: str, out_dir: str):
    """Build the real capture callable: create clip -> wait -> download."""
    from ..ingest.twitch import TwitchClient
    from ..ingest.vod import download_clip_url

    client = TwitchClient(cfg.twitch)

    def capture(spike: Spike) -> tuple[str, str]:
        clip_id = client.create_clip(streamer)
        clip = client.wait_clip(clip_id)
        dst = os.path.join(out_dir, f"live_{clip_id}.mp4")
        download_clip_url(clip["url"], dst)
        return clip_id, dst

    return capture


def run_live(
    streamer: str,
    cfg: Config,
    source: Iterator[tuple[float, str, str]],
    out_dir: str,
    capture=None,
    on_event=None,
    max_events: int | None = None,
) -> list[LiveEvent]:
    """Consume live chat, capture on spikes; returns the events when the
    source ends (stream offline / disconnect) or ``max_events`` is reached.

    ``capture``: callable(Spike) -> (clip_id, clip_path); None = dry run
    (spikes are recorded but nothing is captured).
    ``on_event``: callable(LiveEvent) for progress reporting.
    """
    from ..roster import Roster

    with Roster(cfg.roster_db) as roster:
        roster.require(streamer)

    os.makedirs(out_dir, exist_ok=True)
    events_path = os.path.join(out_dir, "live_events.jsonl")
    detector = SpikeDetector(
        baseline_s=cfg.live.baseline_s,
        window_s=cfg.live.window_s,
        z_threshold=cfg.live.z_threshold,
        min_rate=cfg.live.min_rate,
        cooldown_s=cfg.live.cooldown_s,
        min_baseline_s=cfg.live.min_baseline_s,
    )

    events: list[LiveEvent] = []
    with open(events_path, "a") as events_file:
        for t, _user, _text in source:
            spike = detector.add(t)
            if spike is None:
                continue
            event = LiveEvent(at=spike.at, rate=spike.rate, z=spike.z)
            if capture is not None:
                try:
                    event.clip_id, event.clip_path = capture(spike)
                except Exception as e:  # noqa: BLE001 - keep monitoring on failure
                    event.error = str(e)[:300]
            events.append(event)
            events_file.write(json.dumps(event.__dict__) + "\n")
            events_file.flush()
            if on_event:
                on_event(event)
            if max_events is not None and len(events) >= max_events:
                break
    return events
