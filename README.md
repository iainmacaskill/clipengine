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
- [`docs/first-live-run.md`](docs/first-live-run.md) — checklist for the first
  end-to-end run on real VOD footage: credentials, commands, what to validate.
- [`spike/`](spike/) — scripts from the spike run: mock-VOD generator, transcription
  wrappers (faster-whisper and PocketSphinx), and the trim/reformat/caption pipeline.

## Status

Pre-MVP. Product plan drafted; pipeline scaffolded as a Python package with working
detection (chat velocity + emote spikes + audio energy, fused into ranked windows),
edit (frame-accurate trim, 9:16 facecam-top layout), and captioning (opus-style ASS)
stages, permission-gated ingest (chat replay + VOD downloaders), music-DMCA
screening, and publishing clients for YouTube (Data API v3 resumable upload) and
TikTok (Content Posting API direct-post flow) with OAuth token management and a
music-check gate before every publish. All network integrations are tested against
mocked transports; live runs need real credentials (Google Cloud OAuth client;
TikTok developer app — unaudited apps can only post SELF_ONLY, submit the audit
early). Next: first live run on real VOD footage from a clip-permissive streamer.

## Quick start

```bash
pip install -e ".[dev]"        # + ".[asr]" for faster-whisper captions
pytest

# record a streamer's permission first - ingestion is refused without it
clipengine roster add somestreamer --source published_policy \
    --evidence "https://somestreamer.tv/clip-policy" --credit "@somestreamer in caption"
clipengine roster list

# download a VOD's video (or just a slice of it) and its chat replay
clipengine vod 2274633451 --streamer somestreamer -o vod.mp4 --start 3600 --end 5400
clipengine chat 2274633451 --streamer somestreamer -o chat.jsonl

# score a VOD (chat log optional but strongly recommended)
clipengine detect vod.mp4 --chat chat.jsonl

# render one window as a captioned 9:16 short (facecam auto-detected;
# pass --facecam X,Y,W,H to override)
clipengine render vod.mp4 --start 3721 --end 3796 -o clip.mp4
clipengine facecam vod.mp4        # inspect the detection on its own

# DMCA screen: flag music-likely segments; optionally write a muted copy
clipengine music-check clip.mp4 --mute clip_safe.mp4

# one-time per-account authorisation, then publish (music gate runs first)
clipengine auth youtube                 # prints consent URL; re-run with --code
clipengine publish youtube clip.mp4 --title "Insane clutch" --privacy unlisted
clipengine publish tiktok clip.mp4 --title "insane clutch #gaming"

# list a streamer's recent VODs (needs CLIPENGINE_TWITCH_CLIENT_ID / _SECRET)
clipengine vods somestreamer
```

Chat log format is JSONL: `{"offset": seconds_from_start, "user": "...", "text": "..."}`.

## Package layout

```
clipengine/
  models.py       shared dataclasses (candidates, transcript, signals, ...)
  roster.py       streamer permission roster (SQLite) - gates all ingestion
  config.py       tunable pipeline config (TOML + env overrides)
  pipeline.py     batch orchestration: detect_candidates / render_candidate
  cli.py          command-line entry point
  ingest/         Twitch Helix client (VOD listing works; downloads TODO)
  detect/         chat + audio signal extraction, fusion, optional ASR
  edit/           ffmpeg trim / vertical reformat / subtitle burn / facecam auto-detect
  package/        ASS caption generation + music-DMCA screening/muting
  publish/        YouTube resumable upload + TikTok direct post + OAuth tokens
```

## Pipeline overview

```
INGEST (VOD + chat log) → DETECT (multi-signal highlight scoring)
→ EDIT (cut + 9:16 facecam/gameplay layout) → PACKAGE (captions, hook, metadata)
→ PUBLISH (TikTok / Shorts) → ANALYTICS (per-clip performance → detector tuning)
```

See the product plan for the full architecture and the rights/monetisation strategy
that shapes it.
