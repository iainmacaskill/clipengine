"""End-to-end offline pipeline: source video (+ chat log) -> captioned vertical clips.

This is the batch path the MVP runs per VOD. Network stages (ingest download,
publish) are invoked separately; this module assumes the source video and chat
log are already on disk.
"""
from __future__ import annotations

import json
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


def credit_text_for(streamer: str, roster_credit: str = "") -> str:
    """Overlay text for a streamer: their roster credit format, or the default."""
    return roster_credit.strip() or f"clip: twitch.tv/{streamer.strip().lower()}"


def render_candidate(
    video_path: str,
    candidate: ClipCandidate,
    facecam: FacecamRegion,
    out_path: str,
    cfg: Config,
    with_captions: bool = True,
    credit_text: str | None = None,
) -> str:
    """Cut one candidate, reformat to 9:16, caption, and write the final master."""
    work = cfg.work_dir
    os.makedirs(work, exist_ok=True)
    source = edit.probe(video_path)

    cut = edit.trim(
        video_path, os.path.join(work, "cut.mp4"), candidate.start, candidate.duration, cfg.edit
    )
    vert = edit.vertical(
        cut, os.path.join(work, "vertical.mp4"), source, facecam, cfg.edit,
        credit_text=credit_text,
    )

    if not with_captions:
        os.replace(vert, out_path)
        return out_path

    clip_wav = audio.extract_wav(vert, os.path.join(work, "clip.wav"))
    transcript = transcribe.transcribe(clip_wav)
    ass = captions.write_ass(transcript, os.path.join(work, "captions.ass"), cfg.caption)
    return edit.burn_subtitles(vert, out_path, ass, cfg.edit)


def process_vod(
    video_path: str,
    chat_path: str | None,
    streamer: str,
    out_dir: str,
    cfg: Config,
    top_n: int | None = None,
    with_captions: bool = True,
    facecam: FacecamRegion | None = None,
) -> list[dict]:
    """Whole-VOD batch: detect -> render top-N (credited) -> music screen/mute.

    Writes clips and a manifest.json into ``out_dir`` and returns the manifest.
    The permission roster is checked first (raises PermissionError_ if the
    streamer is not allowed); each clip is screened for music and auto-muted
    when flagged; one clip's failure is recorded and does not stop the batch.
    """
    from .package.music import check as music_check, mute_segments
    from .roster import Roster

    with Roster(cfg.roster_db) as roster:
        entry = roster.require(streamer)
    credit = credit_text_for(streamer, entry.credit)

    os.makedirs(out_dir, exist_ok=True)
    candidates = detect_candidates(video_path, chat_path, cfg)[: top_n or cfg.detect.top_n]

    if facecam is None:
        from .edit.facecam import detect_facecam

        found = detect_facecam(video_path)
        if found is None:
            raise RuntimeError(
                "no facecam detected - pass facecam coordinates explicitly"
            )
        facecam = found.region

    manifest: list[dict] = []
    for i, cand in enumerate(candidates, start=1):
        item: dict = {
            "index": i,
            "start": round(cand.start, 2),
            "end": round(cand.end, 2),
            "score": round(cand.score, 3),
            "signals": {k: round(v, 3) for k, v in cand.signal_breakdown.items()},
            "streamer": streamer,
            "credit": credit,
        }
        out_path = os.path.join(out_dir, f"clip_{i:02d}_{int(cand.start)}s.mp4")
        try:
            render_candidate(
                video_path, cand, facecam, out_path, cfg,
                with_captions=with_captions, credit_text=credit,
            )
            wav = audio.extract_wav(out_path, os.path.join(cfg.work_dir, "screen.wav"))
            segments = music_check(wav)
            if segments:
                muted = out_path.replace(".mp4", "_muted.mp4")
                mute_segments(out_path, muted, segments)
                os.replace(muted, out_path)
                item["muted_segments"] = [
                    {"start": round(s.start, 1), "end": round(s.end, 1)} for s in segments
                ]
            item["path"] = out_path
            item["status"] = "rendered"
        except Exception as e:  # noqa: BLE001 - isolate per-clip failures
            item["status"] = "failed"
            item["error"] = str(e)[:300]
        manifest.append(item)

    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    return manifest
