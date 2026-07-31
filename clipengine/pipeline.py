"""End-to-end offline pipeline: source video (+ chat log) -> captioned vertical clips.

This is the batch path the MVP runs per VOD. Network stages (ingest download,
publish) are invoked separately; this module assumes the source video and chat
log are already on disk.
"""
from __future__ import annotations

import os

from .config import Config
from .detect import audio, chat, fusion, transcribe
from .edit import ffmpeg as edit
from .models import ClipCandidate, FacecamRegion, SignalSeries
from .package import captions


def compute_series(
    video_path: str, chat_path: str | None, cfg: Config
) -> tuple[list[SignalSeries], dict[str, float], float]:
    """Extract all detection signal series once -> (series, config weights, duration)."""
    os.makedirs(cfg.work_dir, exist_ok=True)
    source = edit.probe(video_path)

    series: list[SignalSeries] = []
    weights: dict[str, float] = {}

    wav = audio.extract_wav(video_path, os.path.join(cfg.work_dir, "audio.wav"))
    series.append(audio.energy_series(wav))
    weights["audio_energy"] = cfg.detect.weight_audio_energy

    if chat_path:
        messages = chat.parse_chat_jsonl(chat_path)
        series.append(chat.velocity_series(messages, source.duration))
        series.append(chat.emote_series(messages, source.duration, cfg.detect.emote_tokens))
        weights["chat_velocity"] = cfg.detect.weight_chat_velocity
        weights["chat_emotes"] = cfg.detect.weight_chat_emotes

    return series, weights, source.duration


def detect_candidates(
    video_path: str, chat_path: str | None, cfg: Config
) -> list[ClipCandidate]:
    """Score the timeline and return ranked candidate windows."""
    series, weights, duration = compute_series(video_path, chat_path, cfg)
    return fusion.fuse(series, weights, duration, cfg.detect)


def render_candidate(
    video_path: str,
    candidate: ClipCandidate,
    facecam: FacecamRegion,
    out_path: str,
    cfg: Config,
    with_captions: bool = True,
) -> str:
    """Cut one candidate, reformat to 9:16, caption, and write the final master."""
    work = cfg.work_dir
    os.makedirs(work, exist_ok=True)
    source = edit.probe(video_path)

    cut = edit.trim(
        video_path, os.path.join(work, "cut.mp4"), candidate.start, candidate.duration, cfg.edit
    )
    vert = edit.vertical(cut, os.path.join(work, "vertical.mp4"), source, facecam, cfg.edit)

    if not with_captions:
        os.replace(vert, out_path)
        return out_path

    clip_wav = audio.extract_wav(vert, os.path.join(work, "clip.wav"))
    transcript = transcribe.transcribe(clip_wav)
    ass = captions.write_ass(transcript, os.path.join(work, "captions.ass"), cfg.caption)
    return edit.burn_subtitles(vert, out_path, ass, cfg.edit)
