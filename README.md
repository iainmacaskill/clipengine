# ClipEngine

Automated Twitch-to-Shorts clip pipeline: ingest streams from opted-in streamers,
detect highlight moments with multi-signal AI scoring (chat velocity, audio
excitement, transcript analysis), edit them into vertical short-form video, caption
them, and publish to TikTok and YouTube Shorts — monetised through platform
creator-reward programmes on an own-brand, permissioned clip network.

## Contents

- [`docs/product-plan.md`](docs/product-plan.md) — full product plan: business models,
  rights strategy, pipeline architecture, MVP scope, roadmap, unit economics, risks.
- [`docs/spike-notes.md`](docs/spike-notes.md) — findings from the first technical
  spike (end-to-end pipeline trial using the public `clipify` Claude Code skill).
- [`spike/`](spike/) — scripts from the spike run: mock-VOD generator, transcription
  wrappers (faster-whisper and PocketSphinx), and the trim/reformat/caption pipeline.

## Status

Pre-MVP. Product plan drafted; pipeline scaffolded as a Python package with working
detection (chat velocity + emote spikes + audio energy, fused into ranked windows),
edit (frame-accurate trim, 9:16 facecam-top layout), and captioning (opus-style ASS)
stages, plus a complete ingest pair: chat replay downloader (GQL persisted-query
route) and VOD video downloader (yt-dlp wrapper with quality cap and time-slice
support) — both tested against mocks, pending a first live run. TikTok/YouTube
publishing remains stubbed pending API credentials/audit. Next: run detection on real
VOD footage from a clip-permissive streamer and compare picks against the streamer's
own posted clips.

## Quick start

```bash
pip install -e ".[dev]"        # + ".[asr]" for faster-whisper captions
pytest

# download a VOD's video (or just a slice of it) and its chat replay
clipengine vod 2274633451 -o vod.mp4 --start 3600 --end 5400
clipengine chat 2274633451 -o chat.jsonl

# score a VOD (chat log optional but strongly recommended)
clipengine detect vod.mp4 --chat chat.jsonl

# render one window as a captioned 9:16 short (facecam ROI in source pixels)
clipengine render vod.mp4 --start 3721 --end 3796 --facecam 24,24,420,236 -o clip.mp4

# list a streamer's recent VODs (needs CLIPENGINE_TWITCH_CLIENT_ID / _SECRET)
clipengine vods somestreamer
```

Chat log format is JSONL: `{"offset": seconds_from_start, "user": "...", "text": "..."}`.

## Package layout

```
clipengine/
  models.py       shared dataclasses (candidates, transcript, signals, ...)
  config.py       tunable pipeline config (TOML + env overrides)
  pipeline.py     batch orchestration: detect_candidates / render_candidate
  cli.py          command-line entry point
  ingest/         Twitch Helix client (VOD listing works; downloads TODO)
  detect/         chat + audio signal extraction, fusion, optional ASR
  edit/           ffmpeg trim / vertical reformat / subtitle burn
  package/        ASS caption generation
  publish/        YouTube + TikTok stubs (Phase 2)
```

## Pipeline overview

```
INGEST (VOD + chat log) → DETECT (multi-signal highlight scoring)
→ EDIT (cut + 9:16 facecam/gameplay layout) → PACKAGE (captions, hook, metadata)
→ PUBLISH (TikTok / Shorts) → ANALYTICS (per-clip performance → detector tuning)
```

See the product plan for the full architecture and the rights/monetisation strategy
that shapes it.
