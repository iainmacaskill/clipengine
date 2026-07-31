# Spike notes: clipify trial run (2026-07-29)

Trial of the public **clipify** Claude Code skill
(github.com/louisedesadeleer/clipify) as a prototype of the ClipEngine pipeline
(see `clip-automation-product-plan.md` §4.2, §11 step 4). Run in a Claude Code
remote sandbox.

## What was run

Full pipeline, end to end:

1. **Source:** 72s mock "stream VOD" (1920×1080, facecam box top-left over animated
   gameplay-style visuals, espeak-ng voice track with scripted streamer dialogue
   including a deliberate rage/fail moment). Synthetic because the sandbox network
   policy blocks twitch.tv/youtube.com (and huggingface.co, so Whisper models couldn't
   be fetched — PocketSphinx's bundled English model was substituted for ASR).
2. **Transcribe:** PocketSphinx, word-level timestamps, emitted in Whisper JSON shape.
3. **Detect:** transcript scanned per clipify heuristics (repetition bursts,
   exclamations, reversals). The scripted fail moment surfaced clearly at ~21–38s —
   even through a badly garbled transcript, the *shape* of the signal (repeated
   "wait", stutter bursts) was enough to locate it.
4. **Edit:** frame-accurate 18.6s trim → 9:16 1080×1920, facecam tile top (1080×608) +
   gameplay center-crop bottom (1080×1312) via single ffmpeg filtergraph.
5. **Caption:** clipify's `build_ass.py` generated 51 opus-style word-highlight events
   (3-word chunks, yellow active word); burned in with `subtitles=` filter.

Artifacts (sandbox-local, not committed): `/tmp/clipify/` — source, transcript,
ASS file, final master + preview.

## Findings

- **The mechanics are commodity.** Transcribe → detect → trim → reframe → caption →
  render worked end to end in one session with zero custom video code. clipify's ASS
  caption generator and pan/analyze scripts are directly reusable; its SKILL.md
  workflow matches our planned stages 2–4 almost exactly.
- **Detection survives bad ASR.** The funny-moment heuristics fired on repetition/
  exclamation *patterns*, not exact words — supports the plan's bet that cheap signals
  (chat velocity + audio energy) can drive selection, with transcript quality mattering
  mainly for captions, not detection.
- **Caption quality is fully ASR-bound.** Garbled words go straight onto the screen.
  Production needs real Whisper (word error rate matters for the burned captions far
  more than for detection).
- **clipify gaps vs. our product:** no chat-log signal, no >60s duration targeting
  (its 10–25s default is below TikTok Creator Rewards' 1-minute pay floor), no
  music-DMCA check, no publish/schedule stage, single-clip interactive flow rather
  than batch. These are exactly the differentiators in the product plan.
- **Environment note:** this sandbox's network policy blocks Twitch/YouTube/HF, so a
  real-footage rerun needs either a network-open environment or local execution.

## Next step

Rerun on real VOD footage from a clip-permissive streamer (with Whisper proper), and
compare detector picks against the streamer's own posted clips — the §11 step 4
validation the plan calls for.
