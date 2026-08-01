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

    if cfg.detect.game_profile:
        from .detect import gamecv

        game_series, _hits = gamecv.detect_events(
            video_path, cfg.detect.game_profile, source.duration
        )
        series.append(game_series)
        weights["game_events"] = cfg.detect.weight_game_events

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
    transcript_out: str | None = None,
) -> str:
    """Cut one candidate, reformat to 9:16, caption, and write the final master.

    When captions are generated, the clip-relative transcript is also saved to
    ``transcript_out`` (JSON) if given - downstream stages (hook/title
    generation) reuse it instead of re-transcribing.
    """
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
    if transcript_out:
        transcribe.save(transcript, transcript_out)
    ass = captions.write_ass(transcript, os.path.join(work, "captions.ass"), cfg.caption)
    return edit.burn_subtitles(vert, out_path, ass, cfg.edit)


def snap_to_speech(
    transcript,
    start: float,
    end: float,
    max_shift: float = 4.0,
    pad: float = 0.2,
) -> tuple[float, float]:
    """Snap a cut window to sentence boundaries so it never opens or closes
    mid-sentence.

    Start: if it lands inside a spoken segment, pull it back to that
    sentence's beginning (within ``max_shift`` seconds), else push it forward
    to the next sentence's start. End: extend to let the current sentence
    finish (within ``max_shift``), else retreat to just before it began.
    Boundaries in silence are left alone; ``pad`` keeps a breath of space
    around the speech.
    """
    segs = transcript.segments
    new_start, new_end = start, end
    for s in segs:
        if s.start < start < s.end:  # opens mid-sentence
            if start - s.start <= max_shift:
                new_start = s.start
            else:
                nxt = [g.start for g in segs if g.start >= start]
                if nxt:
                    new_start = min(nxt)
            break
    for s in segs:
        if s.start < end < s.end:  # closes mid-sentence
            if s.end - end <= max_shift:
                new_end = s.end
            else:
                new_end = s.start
            break
    new_start = max(0.0, new_start - pad)
    new_end = new_end + pad
    if new_end - new_start < 1.0:  # degenerate after snapping - keep original
        return start, end
    return round(new_start, 2), round(new_end, 2)


def source_transcript(video_path: str, cfg: Config):
    """Transcribe a source once, cached beside it as <file>.transcript.json -
    a batch of windows over the same master must not re-transcribe it."""
    cache = video_path + ".transcript.json"
    if os.path.exists(cache):
        return transcribe.load(cache)
    os.makedirs(cfg.work_dir, exist_ok=True)
    wav = audio.extract_wav(
        video_path, os.path.join(cfg.work_dir, "source_snap.wav")
    )
    transcript = transcribe.transcribe(wav)
    transcribe.save(transcript, cache)
    return transcript


def repurpose_asset(
    video_path: str,
    out_path: str,
    cfg: Config,
    hook: str | None = None,
    cta: str | None = None,
    credit_text: str | None = None,
    start: float | None = None,
    end: float | None = None,
    with_captions: bool = True,
    transcript_out: str | None = None,
) -> str:
    """Repurpose provided asset footage (UGC/reposting campaigns): optional trim
    -> fit-to-9:16 over a blurred self-fill (no facecam) -> captions when the
    asset has speech -> hook burned over the open. The campaign-mandated CTA
    and credit are drawn into the frame.
    """
    work = cfg.work_dir
    os.makedirs(work, exist_ok=True)
    source = edit.probe(video_path)

    src = video_path
    if start is not None or end is not None:
        begin = start or 0.0
        duration = (end if end is not None else source.duration) - begin
        src = edit.trim(video_path, os.path.join(work, "cut.mp4"), begin, duration, cfg.edit)

    vert = edit.vertical_fit(
        src, os.path.join(work, "vertical.mp4"), source, cfg.edit,
        credit_text=credit_text, cta_text=cta,
    )

    stage = vert
    if with_captions:
        clip_wav = audio.extract_wav(vert, os.path.join(work, "clip.wav"))
        transcript = transcribe.transcribe(clip_wav)
        if transcript.segments:  # assets without speech skip captions cleanly
            if transcript_out:
                transcribe.save(transcript, transcript_out)
            ass = captions.write_ass(
                transcript, os.path.join(work, "captions.ass"), cfg.caption
            )
            stage = edit.burn_subtitles(
                vert, os.path.join(work, "captioned.mp4"), ass, cfg.edit
            )

    if hook:
        return edit.burn_hook(stage, out_path, hook, cfg.edit)
    os.replace(stage, out_path)
    return out_path


def process_vod(
    video_path: str,
    chat_path: str | None,
    streamer: str,
    out_dir: str,
    cfg: Config,
    top_n: int | None = None,
    with_captions: bool = True,
    facecam: FacecamRegion | None = None,
    suggest=None,
    campaign=None,
) -> list[dict]:
    """Whole-VOD batch: detect -> render top-N (credited) -> music screen/mute
    -> LLM hook/title/hashtags (when configured).

    Writes clips and a manifest.json into ``out_dir`` and returns the manifest.
    The permission roster is checked first (raises PermissionError_ if the
    streamer is not allowed); each clip is screened for music and auto-muted
    when flagged; one clip's failure is recorded and does not stop the batch.

    ``suggest`` is a callable(transcript_text, streamer) -> hooks.Suggestion|None;
    when None it defaults to Claude via package.hooks if an API key is present.
    Suggestions need a transcript, so they only run when captions are on.

    ``campaign`` (a campaigns.models.Campaign) applies that campaign's render
    template: the detection window is steered inside the campaign's duration
    bounds, the mandated credit is burned alongside the roster credit, every
    clip gets a ready-to-post caption carrying the required hashtags/mentions,
    and the compliance gate report is recorded per clip in the manifest.
    """
    import copy

    from .package import hooks
    from .package.music import check as music_check, mute_segments
    from .roster import Roster

    if suggest is None and hooks.available():
        suggest = lambda text, s: hooks.generate(text, s)  # noqa: E731

    with Roster(cfg.roster_db) as roster:
        entry = roster.require(streamer)
    credit = credit_text_for(streamer, entry.credit)

    template = None
    if campaign is not None:
        from .campaigns.template import effective_target, merge_credit, template_for

        template = template_for(campaign)
        target = effective_target(template, cfg.detect.target_duration)
        if target != cfg.detect.target_duration:
            cfg = copy.deepcopy(cfg)
            cfg.detect.target_duration = target
        credit = merge_credit(credit, template)

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
        transcript_path = out_path.replace(".mp4", ".transcript.json")
        try:
            render_candidate(
                video_path, cand, facecam, out_path, cfg,
                with_captions=with_captions, credit_text=credit,
                transcript_out=transcript_path,
            )
            if suggest and os.path.exists(transcript_path):
                transcript = transcribe.load(transcript_path)
                text = " ".join(s.text.strip() for s in transcript.segments)
                suggestion = suggest(text, streamer)
                if suggestion:
                    item["hook"] = suggestion.hook
                    item["suggested_title"] = suggestion.title
                    item["hashtags"] = suggestion.hashtags
                    if cfg.llm.burn_hook and suggestion.hook:
                        hooked = out_path.replace(".mp4", "_hooked.mp4")
                        edit.burn_hook(out_path, hooked, suggestion.hook, cfg.edit)
                        os.replace(hooked, out_path)
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
            if template is not None:
                from .campaigns.gate import ClipFacts, preflight
                from .campaigns.template import build_caption

                caption = build_caption(item.get("suggested_title", ""), template)
                report = preflight(
                    ClipFacts(
                        duration_s=cand.duration,
                        caption=caption,
                        credit_text=credit,
                    ),
                    template.checklist,
                    campaign,
                )
                item["campaign"] = campaign.id
                item["caption"] = caption
                item["gate"] = {
                    "passed": report.passed,
                    "failures": [r.detail for r in report.failures],
                    "manual": [r.detail for r in report.manual],
                }
        except Exception as e:  # noqa: BLE001 - isolate per-clip failures
            item["status"] = "failed"
            item["error"] = str(e)[:300]
        manifest.append(item)

    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    return manifest
