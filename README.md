# ClipEngine

Automated stream-to-Shorts clip pipeline: discover paid clipping campaigns on
Whop Content Rewards, ingest their authorised source material, detect highlight
moments with multi-signal AI scoring (chat velocity, audio excitement, transcript
analysis), edit them into vertical short-form video, caption them, and publish to
TikTok and YouTube Shorts — monetised through campaign CPM/bounty payouts, with
platform creator-reward programmes as a secondary channel.

## Contents

- [`docs/whop-clipping-dev-brief.md`](docs/whop-clipping-dev-brief.md) — the
  governing dev brief for the Whop Content Rewards pivot: phases, hard lines,
  milestones. Companions: [prior art](docs/whop-clipping-prior-art.md),
  [Whop SDK audit](docs/whopsdk-python-audit.md),
  [revenue research](docs/research-twitch-clipping-revenue.md).
- [`docs/product-plan.md`](docs/product-plan.md) — original product plan (pre-pivot):
  business models, rights strategy, pipeline architecture, unit economics, risks.
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
music-check gate before every publish. The full pipeline passed a synthetic
dress rehearsal ([results](docs/dress-rehearsal-2026-08.md)). Now pivoting to
the [Whop Content Rewards brief](docs/whop-clipping-dev-brief.md): Phase 1
campaign intelligence is in (`clipengine campaigns` — read-only Workforce
Bounties discovery, EV scoring, rules parsing, launch alerts). All network
integrations are tested against mocked transports; live runs need real
credentials (Whop API key; Google Cloud OAuth client; TikTok developer app —
unaudited apps can only post SELF_ONLY, submit the audit early).

## Quick start

```bash
pip install -e ".[dev]"        # + ".[asr]" for faster-whisper captions
pytest

# campaign intelligence (Whop Content Rewards): discover open clipping bounties
# (read-only; needs CLIPENGINE_WHOP_API_KEY), score them, alert on launches
clipengine campaigns sync
clipengine campaigns list --status open --top 10
clipengine campaigns show bnty_xxx            # score breakdown, rules, budget history

# CPM-per-views campaigns have no public API. Automated option: parse the
# public discover feed (read-only), ranked by best rewards - rate x remaining
# budget x familiarity, with nearly-exhausted pools sunk. If the CDN refuses
# the fetch, save the page from your browser and use --file
clipengine campaigns discover --top 10 --min-cpm 0.75 --add
clipengine campaigns discover --file saved_page.html --sort rate
# the feed has no rules text - attach each campaign's brief before producing
clipengine campaigns rules disc:some-campaign --attach brief.txt

# or key campaigns in manually
clipengine campaigns add --title "Neon clips" --cpm 2 --budget 5000 \
    --platforms tiktok,youtube --rules-file campaign_brief.txt
clipengine campaigns rules --file campaign_brief.txt   # preview the parsed checklist

# compliance gate: pre-flight a clip + caption against a campaign's rules -
# duration, hashtags, mentions, platform, budget still live, source. Machine-
# checkable rules pass/fail; the rest surface as manual confirmation items
clipengine campaigns check clip.mp4 --campaign manual:neon-clips \
    --caption "insane clutch #NeonClips @neon" --platform tiktok
# publish and queue add enforce the same gate with --campaign: a failing
# clip is refused (every rejected submission is unpaid work)
clipengine publish tiktok clip.mp4 --title "clutch #NeonClips @neon" --campaign manual:neon-clips

# submission tracker: record each Whop submission (made through the normal web
# flow - no submission API exists), then track pending -> approved (48h
# auto-approval window) -> paid, with rejection reasons feeding scoring
clipengine submissions add manual:neon-clips https://tiktok.com/@acct/video/123 \
    --platform tiktok --account acct1
clipengine submissions sync                    # advance pending past the 48h window
clipengine submissions views 1 42000
clipengine submissions paid 1 --amount 84      # or: reject 1 --reason "credit missing"
clipengine submissions stats                   # per-campaign revenue, effective CPM,
                                               # rejection rate vs the <15% target
clipengine submissions reconcile --user user_xxx --ledger ldgr_xxx   # vs Whop balance

# record a streamer's permission first - ingestion is refused without it
clipengine roster add somestreamer --source published_policy \
    --evidence "https://somestreamer.tv/clip-policy" --credit "@somestreamer in caption"
clipengine roster list

# or bulk-import the roster from CSV (template: docs/roster-template.csv)
clipengine roster import streamers.csv
clipengine roster export -o roster_backup.csv

# download a VOD's video (or just a slice of it) and its chat replay
clipengine vod 2274633451 --streamer somestreamer -o vod.mp4 --start 3600 --end 5400
clipengine chat 2274633451 --streamer somestreamer -o chat.jsonl

# score a VOD (chat log optional but strongly recommended)
clipengine detect vod.mp4 --chat chat.jsonl

# or do detect -> render top-N (credited) -> music screen -> queue in ONE command
clipengine process vod.mp4 --chat chat.jsonl --streamer somestreamer -o clips/ \
    --top 5 --queue-platform youtube --account mychannel

# --campaign applies that campaign's render template: detection windows are
# steered inside the campaign's duration bounds, the mandated credit is burned
# in alongside the roster credit, every clip gets a ready-to-post caption with
# the required hashtags/mentions, and the gate report lands in the manifest;
# gate-failing clips are never queued. Compliance is baked in, not checked after
clipengine process vod.mp4 --chat chat.jsonl --streamer somestreamer -o clips/ \
    --campaign manual:neon-clips --queue-platform tiktok --account acct1

# LIVE mode: watch a stream's chat, capture Twitch clips on hype spikes
# (clip creation needs CLIPENGINE_TWITCH_USER_TOKEN with the clips:edit scope)
clipengine live somestreamer -o live_clips/ --dry-run     # detect only, calibrate
clipengine live somestreamer -o live_clips/               # capture + download

# human review: import the batch, approve (with real titles) into the publish
# queue or reject with a reason; stats tracks the MVP >=50% pass-rate criterion
clipengine review import clips/manifest.json
clipengine review approve 1 --title "INSANE 1v5 clutch" --queue-platform youtube --account mychannel
clipengine review reject 2 --reason "cut too early"
clipengine review stats

# game-event CV: scan with a per-game template profile (killfeeds, victory
# screens); set [detect] game_profile in config to add it as a fusion signal
clipengine game-events vod.mp4 --profile profiles/league-of-legends/

# tune detector weights against what viewers actually clipped
clipengine truth <vod_id> --streamer somestreamer -o truth.json
clipengine tune vod.mp4 --chat chat.jsonl --truth truth.json --write-config tuned.toml

# repurpose campaign-provided asset footage (UGC/reposting campaigns): any
# aspect ratio -> 9:16 over a blurred self-fill, captions when the asset has
# speech, hook over the open, CTA + credit drawn in; --campaign builds the
# compliant caption and runs the gate on the result
clipengine repurpose asset.mp4 -o post1.mp4 --campaign disc:some-campaign \
    --hook "this AI builds Roblox GUIs" --cta "link in bio" --platform tiktok

# render one window as a captioned 9:16 short (facecam auto-detected;
# pass --facecam X,Y,W,H to override). --streamer burns their roster credit
# into the clip; --no-credit is allowed only for private test renders
clipengine render vod.mp4 --start 3721 --end 3796 --streamer somestreamer -o clip.mp4
clipengine facecam vod.mp4        # inspect the detection on its own

# LLM hook/title/hashtags for a clip (needs ANTHROPIC_API_KEY + clipengine[llm]);
# process runs this automatically per clip and burns the hook over the first 2.5s
clipengine suggest clip.mp4 --streamer somestreamer

# DMCA screen: flag music-likely segments; optionally write a muted copy
clipengine music-check clip.mp4 --mute clip_safe.mp4

# one-time per-account authorisation, then publish (music gate runs first)
clipengine auth youtube                 # prints consent URL; re-run with --code
clipengine publish youtube clip.mp4 --title "Insane clutch" --privacy unlisted
clipengine publish tiktok clip.mp4 --title "insane clutch #gaming"

# or queue instead of publishing immediately: slots respect posting windows,
# per-account spacing, and daily caps ([schedule] section in config TOML)
clipengine queue add youtube clip.mp4 --account mychannel --title "Insane clutch"
clipengine queue list
clipengine queue run          # publishes everything due - run from cron every ~15min

# performance loop: snapshot stats for published posts, then report
clipengine stats sync         # cron this daily (or more often for velocity data)
clipengine stats report --csv performance.csv

# scheduled operation: install the three sync jobs (campaigns every 10 min,
# submissions hourly, stats daily) into your crontab - idempotent, and your
# existing crontab entries are left untouched. Secrets go in ~/.clipengine/env
# (copy ops/env.example), logs land in ~/.clipengine/logs/
ops/install-cron.sh                    # or --with-queue-run / --remove


# list a streamer's recent VODs (needs CLIPENGINE_TWITCH_CLIENT_ID / _SECRET)
clipengine vods somestreamer
```

Chat log format is JSONL: `{"offset": seconds_from_start, "user": "...", "text": "..."}`.

## Package layout

```
clipengine/
  models.py       shared dataclasses (candidates, transcript, signals, ...)
  roster.py       streamer permission roster (SQLite) - gates all ingestion
  campaigns/      Whop campaign intelligence: read-only bounty discovery,
                  EV scoring, rules-text -> compliance checklist, launch alerts,
                  pre-export compliance gate (enforced by publish/queue),
                  per-campaign render templates (compliance baked into renders),
                  submission tracker (pending -> approved -> paid + earnings)
  analytics.py    performance snapshots + reporting for published posts
  review.py       human review queue - pass-rate metric, approvals feed publishing
  config.py       tunable pipeline config (TOML + env overrides)
  pipeline.py     batch orchestration: detect_candidates / render_candidate
  cli.py          command-line entry point
  ingest/         Twitch Helix client (VOD listing works; downloads TODO)
  detect/         chat + audio signal extraction, game-event template CV,
                  fusion, optional ASR, weight tuning vs viewer-clipped truth
  edit/           ffmpeg trim / vertical reformat / subtitle burn / facecam auto-detect
  package/        ASS captions + music-DMCA screening + LLM hooks/titles/hashtags
  live/           live mode: IRC chat monitor, spike detector, clip capture
  publish/        YouTube resumable upload + TikTok direct post + OAuth tokens
                  + scheduling queue (posting windows, spacing, daily caps)
```

## Pipeline overview

```
INGEST (VOD + chat log) → DETECT (multi-signal highlight scoring)
→ EDIT (cut + 9:16 facecam/gameplay layout) → PACKAGE (captions, hook, metadata)
→ PUBLISH (TikTok / Shorts) → ANALYTICS (per-clip performance → detector tuning)
```

See the product plan for the full architecture and the rights/monetisation strategy
that shapes it.
