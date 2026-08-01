# Dress rehearsal — full-pipeline test run (2026-08-01)

Synthetic end-to-end run in a sandboxed environment (Twitch/YouTube/HF blocked, no
API credentials). Source: a generated 360s "VOD" (720p, facecam box, credit-worthy
layout) with three engineered moments — rage at ~92-110s, hype-with-music-bed at
~200-232s, victory (on-screen banner) at ~300-318s — plus a decoy chat burst at
~150s with nothing on screen. 834 synthetic chat messages correlated with the
moments; truth file listing the three moments views-descending.

## Results by stage

| Stage | Result |
|---|---|
| detect (default weights) | **3/3 moments in the top 3 candidates**, correct signal attribution (music moment carried by audio; others by chat/emotes); decoy burst correctly ranked last |
| tune vs truth | recall@4 = 1.00; many configs tie (expected: 3 strong moments on synthetic data — real discrimination needs 10+ noisy truth moments) |
| process (batch) | 3/3 rendered in **84s wall-clock** for 3×40s clips at 720p, credit burned, facecam auto-detected |
| music-DMCA screen | **flagged and auto-muted only the music clip** (span 9.5-40.5 clip-time vs true bed 12-44): muted span -91dB, clean speech -32dB; other clips untouched |
| review | import → approve 2 (queued with real titles) / reject 1 with reason → stats: 67% pass rate, MVP >=50% criterion reported MET |
| queue | slots assigned per windows/spacing (09:45, 11:45 at 2h spacing); `queue run` correctly idle before the slot |
| game-events CV | victory template hit at **exactly 300.0s, score 1.00**, min-gap dedup to a single event |
| 4-signal fusion | with game profile enabled, victory clip score 3.01 → **4.62** (game_events +1.33), lead widened |
| live monitor (scripted chat) | spike detected **0.3s into the burst** (z=3.0), roster-gated, event logged; dry-run correctly skipped capture |
| hooks/titles | skipped gracefully (no ANTHROPIC_API_KEY) — pipeline unaffected, as designed |

## Findings / notes

1. **Facecam auto-detect drifted right** on this synthetic layout (crop cut the left
   edge of the facecam box). Known behaviour on adversarial test patterns; verify on
   real stream layouts and use `--facecam` override if needed.
2. **Muted-clip UX**: a 30s mute inside a 40s clip is technically correct but
   editorially dead (the review rejection in this run). Real flow: prefer trimming
   the candidate window around the music, or replacing rather than muting — a
   Phase-3 refinement; review catches it meanwhile.
3. Tuner needs real, plentiful truth data to discriminate — as documented.
4. Timing datapoint: ~28s/clip end-to-end (720p, no captions, no hooks) on sandbox
   CPU — comfortably inside the $0.15/clip compute target.

## Not exercised (needs real network/credentials — first-live-run checklist)

Chat/VOD downloads against real Twitch; Whisper captions; live IRC against real
chat; Twitch clip creation; YouTube/TikTok auth + publish; stats sync; hook
generation against the real API.
