# First live run — checklist

Goal: one real VOD from a clip-permissive streamer, end to end — chat → detect →
download slice → render → DMCA screen → publish (private/SELF_ONLY) — and a verdict
on detection quality. Everything below runs on a machine with normal internet access
(not a sandboxed environment); total hands-on time excluding waits is ~1 hour.

## 1. Install

```bash
git clone https://github.com/iainmacaskill/clipengine && cd clipengine
python3 -m venv venv && source venv/bin/activate
pip install -e ".[dev,asr,download]"
pytest                      # expect: 56 passed
ffmpeg -version             # install via brew/apt if missing
```

The first `render` with captions downloads the faster-whisper `tiny.en` model
(~75 MB) from Hugging Face automatically.

## 2. Credentials

Only Twitch is needed for the core validation; YouTube/TikTok can follow later.

- [ ] **Twitch** (for `clipengine vods` listing; optional — VOD ids also visible on
  twitch.tv): dev.twitch.tv console → Register application →
  `export CLIPENGINE_TWITCH_CLIENT_ID=... CLIPENGINE_TWITCH_CLIENT_SECRET=...`
- [ ] **YouTube**: Google Cloud Console → new project → enable *YouTube Data API v3*
  → OAuth client (Desktop app) → `export CLIPENGINE_YT_CLIENT_ID=... _SECRET=...`
  Note: uploads cost 1600 quota units of the 10k/day default (~6 uploads/day);
  request a quota increase when multi-channel operation starts.
- [ ] **TikTok**: developers.tiktok.com → register app, request `video.publish` →
  `export CLIPENGINE_TT_CLIENT_KEY=... _SECRET=...`
  **Submit the content-posting audit immediately** — until it passes, posts are
  forced to SELF_ONLY visibility. Longest external lead time in the project.
- [ ] **Anthropic (optional but recommended)**: `export ANTHROPIC_API_KEY=...` +
  `pip install -e ".[llm]"` — enables automatic hook/title/hashtag generation
  during `process` (~a cent per clip). Without it the pipeline runs unchanged,
  just without suggestions.
- [ ] **Twitch user token (optional, live mode)**: a user OAuth token with the
  `clips:edit` scope as `CLIPENGINE_TWITCH_USER_TOKEN` — only needed for
  `clipengine live` clip capture; the dry-run calibration below works without it.

## 3. Pick the source and record permission

- [ ] Choose a streamer with a published clip/content-creation policy (start the
  roster with streamers who already allow clipping publicly — zero negotiation).
- [ ] Record it before anything downloads — ingestion is refused otherwise:

```bash
clipengine roster add <streamer> --source published_policy \
    --evidence "<URL of their clip policy>" --credit "@<handle> in caption"
```

- [ ] Pick a recent VOD with chat activity (2-6h is ideal). Get the id from
  `clipengine vods <streamer>` or the `twitch.tv/videos/<id>` URL.

## 4. The run

```bash
# 1. chat first - it is tiny and drives everything else
clipengine chat <vod_id> --streamer <streamer> -o chat.jsonl

# 2. score the timeline. Detection needs the audio, so either pull the full VOD
#    at low quality, or start chat-only by editing weights (see Troubleshooting)
clipengine vod <vod_id> --streamer <streamer> -o vod.mp4 --max-height 720
clipengine detect vod.mp4 --chat chat.jsonl > candidates.json
cat candidates.json

# 3. sanity-check the facecam detection
clipengine facecam vod.mp4

# 4. render the top candidate (start/end from candidates.json; --streamer burns
#    their roster credit in). Or skip 2-4 and run the whole batch in one command:
#    clipengine process vod.mp4 --chat chat.jsonl --streamer <streamer> -o clips/
#    (renders top-N credited clips, music-screens, and - with ANTHROPIC_API_KEY -
#    generates hooks/titles/hashtags and burns the hook into the first 2.5s)
clipengine render vod.mp4 --start <S> --end <E> --streamer <streamer> -o clip1.mp4

# 5. DMCA screen (also runs automatically inside publish)
clipengine music-check clip1.mp4

# 6. publish privately
clipengine auth youtube            # once; then re-run with --code <code>
clipengine publish youtube clip1.mp4 --title "<hook>" --privacy private
clipengine auth tiktok
clipengine publish tiktok clip1.mp4 --title "<hook>"   # SELF_ONLY until audit
```

## 5. What to actually validate (the point of the run)

- [ ] **Detection vs. ground truth** — the core bet, now automated:

  ```bash
  clipengine truth <vod_id> --streamer <streamer> -o truth.json   # viewer-clipped moments
  clipengine tune vod.mp4 --chat chat.jsonl --truth truth.json --write-config tuned.toml
  ```

  The report shows recall@N per weight config — the default-weights row is the
  validation number (plan target: top-10 windows cover the majority of the top
  viewer-clipped moments), and the best row is the tuned config to adopt.
  A VOD with 10+ viewer clips gives meaningful discrimination; fewer and most
  configs tie at the same recall.
- [ ] **Facecam box** — is the score >0.4 and the box right? Screenshot one frame
  with the box burned in if unsure. Streams that switch scenes mid-VOD will
  confuse it (known limitation).
- [ ] **Caption quality** — real Whisper this time; check word accuracy and timing
  on the rendered clip. If weak, try `--model small.en` (edit detect/transcribe
  default) and note the speed difference.
- [ ] **Music screen on real audio** — run `music-check` on a segment you know has
  game music under voice, and on clean talking. Note scores; the 0.30 threshold
  was calibrated on synthetic audio and probably needs tuning here.
- [ ] **Timing + cost** — wall-clock per stage on your hardware; this feeds the
  $/clip compute model in the product plan (§8).
- [ ] **Hook/title quality (if ANTHROPIC_API_KEY set)** — are the generated
  hooks/titles postable as-is, or do they need editing? Note the edit rate.
- [ ] **Live-mode calibration (optional, no clips created)** — while the streamer
  is live: `clipengine live <streamer> -o live_test/ --dry-run` for ~an hour.
  Do spike counts feel right (a few per hour, at genuinely hype moments)? Tune
  the `[live]` thresholds in config and note chat size vs settings.

Write the numbers into `docs/live-run-notes.md` (create it) — they drive the next
iteration of detector weights and thresholds.

## 6. Troubleshooting

| Symptom | Fix |
|---|---|
| `chat` fails with PersistedQueryNotFound | Twitch rotated the GQL hash: update `PERSISTED_QUERY_HASH` in `ingest/chat_replay.py` (grab from TwitchDownloader source or web-client network tab) |
| `vod` download slow / huge | add `--start/--end` around the candidate windows; drop `--max-height` to 480 for detection-only pulls |
| chat-only detection wanted (skip full VOD pull) | set `weight_audio_energy = 0` in a config TOML and pass a short slice as the video; audio signal only needs the slices you'll render anyway |
| `facecam` returns nothing / wrong box | pass `--facecam X,Y,W,H` manually to `render` (read coordinates from a screenshot); note it in the run notes |
| whisper model download blocked | corporate proxy: pre-download `tiny.en` via huggingface-cli on another network |
| YouTube 403 quotaExceeded | you spent the day's 10k units (6 uploads); wait for reset (midnight PT) or request increase |
| TikTok post invisible to others | expected pre-audit: SELF_ONLY is forced. Check the account's own feed |

## 7. After the run

- [ ] Commit `docs/live-run-notes.md` with the validation numbers.
- [ ] Tune: detector weights / `target_duration` / music threshold based on notes.
- [ ] If detection quality holds: start the roster outreach list (plan §11 step 1)
  and stand up the first channel. If it doesn't: iterate weights on this VOD's
  data before touching more footage — it is now a labelled test set.
