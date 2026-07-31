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

Pre-MVP. Product plan drafted; pipeline mechanics validated end to end on synthetic
footage. Next: rerun the spike on real VOD footage from a clip-permissive streamer
and compare detector picks against the streamer's own posted clips.

## Pipeline overview

```
INGEST (VOD + chat log) → DETECT (multi-signal highlight scoring)
→ EDIT (cut + 9:16 facecam/gameplay layout) → PACKAGE (captions, hook, metadata)
→ PUBLISH (TikTok / Shorts) → ANALYTICS (per-clip performance → detector tuning)
```

See the product plan for the full architecture and the rights/monetisation strategy
that shapes it.
