# Prior Art: Existing GitHub Projects vs the Whop Clipping Brief

*Research date: August 2026*
*Companion docs: [dev brief](whop-clipping-dev-brief.md) · [market research](research-twitch-clipping-revenue.md)*

Survey of existing open-source projects mapped against the three phases of
the [development brief](whop-clipping-dev-brief.md). Found via public web
search of github.com.

## Headline conclusion

**No single project delivers the brief end to end.** The landscape splits
cleanly:

- **Phase 2 (clip production) is well covered** — mature open-source
  options exist for both highlight detection and shorts rendering, and we
  should build on them rather than from scratch.
- **Phase 3 (posting/scheduling) is partially covered** — upload
  automation exists but is the most ToS-fragile category.
- **Phase 1 (Whop campaign intelligence) has essentially no open-source
  prior art.** Nothing discovers, scores, or tracks Content Rewards
  campaigns. This is the gap — and the differentiator the brief targets.

## Phase 1 — Whop campaign intelligence

| Project | What it does | Relevance |
|---|---|---|
| [whopio/whopsdk-python](https://github.com/whopio/whopsdk-python) | **Official Whop Python SDK** | Best starting point for API access; check whether Content Rewards endpoints are exposed |
| [whopio/whopsdk-typescript](https://github.com/whopio/whopsdk-typescript), [whop-go-sdk](https://github.com/whopio/whop-go-sdk), [whopsdk-ruby](https://github.com/whopio/whopsdk-ruby) | Official SDKs, other languages | Same, if we change stack |
| [whopio/whop-tutorials](https://github.com/whopio/whop-tutorials), [whop-app-examples](https://github.com/whopio/whop-app-examples) | Official example apps for the Whop API | Reference for auth/app model |
| [wheblabs/whop-client](https://github.com/wheblabs/whop-client) | Unofficial Whop account SDK (auth, app/company management) | Fallback if official SDK lacks needed surface; higher ToS/maintenance risk |

**Finding:** nothing exists for campaign discovery, EV scoring, budget
tracking, or rules parsing. Action item for the team: audit
`whopsdk-python` and docs.whop.com first — if Content Rewards campaign
data is exposed via the official API, Phase 1's "defensive scraping"
assumption in the brief can be replaced with a supported integration.

## Phase 2a — Highlight detection

Chat-signal projects (align with the brief's chat-spike approach):

| Project | Approach |
|---|---|
| [joaohenggeler/twitch-chat-highlights](https://github.com/joaohenggeler/twitch-chat-highlights) | Chat keywords/emote frequency over time |
| [hougesen/twitch-highlight-finder](https://github.com/hougesen/twitch-highlight-finder) | Chat message + emote frequency analysis |
| [xurei/twitch-highlights-logger](https://github.com/xurei/twitch-highlights-logger) | Windowed chat-message counting with filters/thresholds |
| [packsun/chatplot](https://github.com/packsun/chatplot) | Chat concentration plotting to locate highlights |
| [dscig/twitch-highlight-detection](https://github.com/dscig/twitch-highlight-detection) | PyTorch classifier: popular vs ordinary moments |
| [artkulak/twitch-stream-highlights-detection](https://github.com/artkulak/twitch-stream-highlights-detection) | Real-time ML highlight detection |

Multi-signal / audio-video projects:

| Project | Approach |
|---|---|
| [porplax/auto-highlighter](https://github.com/porplax/auto-highlighter) | Audio/video candidate detection, saves clips for manual review — matches our compliance-gate philosophy |
| [Dietech/TwitchHack](https://github.com/Dietech/TwitchHack) | Chat + audio extraction from VODs → short mp4 clips |
| [bendawg2010/Auto-clipper](https://github.com/bendawg2010/Auto-clipper) | YOLO object detection, pixel analysis, voice-triggered clipping |

**Finding:** the brief's detection stack (chat spikes + audio energy +
transcript scoring) is validated by multiple existing implementations.
Most are small/stale; treat them as reference implementations to adapt,
not dependencies to import.

## Phase 2b — Shorts rendering (9:16, captions)

| Project | What it does |
|---|---|
| [SamurAIGPT/AI-Youtube-Shorts-Generator](https://github.com/SamurAIGPT/AI-Youtube-Shorts-Generator) | Open-source Opus Clip alternative: LLM highlight detection, Whisper transcription, auto vertical cropping; no watermarks |
| [Shaarav4795/ClippedAI](https://github.com/Shaarav4795/ClippedAI) | OpusClip alternative built on Whisper via the `clipsai` library |
| [mutonby/openshorts](https://github.com/mutonby/openshorts) | Self-hosted AI video platform: clip generator + direct posting to TikTok/Reels/Shorts with scheduling |
| GitHub topics: [opus-clip-alternative](https://github.com/topics/opus-clip-alternative), [video-to-shorts](https://github.com/topics/video-to-shorts), [auto-clip](https://github.com/topics/auto-clip) | Active ecosystem of faster-whisper + ffmpeg renderers with burned-in word captions |

**Finding:** the faster-whisper + ffmpeg + burned-captions stack in the
brief is the established pattern. `AI-Youtube-Shorts-Generator` and the
`clipsai` library are the strongest build-on candidates. None support
per-campaign compliance templates (required hashtags/credit overlays) —
that layer is ours to build.

## Phase 3 — Posting, submission and tracking

| Project | What it does | Caution |
|---|---|---|
| [mutonby/openshorts](https://github.com/mutonby/openshorts) | Direct posting to TikTok/Reels/Shorts via Upload-Post, with scheduling | Verify it uses official APIs before adopting |
| [natecode880/python-youtube-automator](https://github.com/natecode880/python-youtube-automator) | YouTube Data API v3 upload scheduler | Official API — aligned with the brief |
| [teja156/autobot-clipper](https://github.com/teja156/autobot-clipper) | Full Twitch → YouTube automation loop (closest single project to the whole pipeline, minus Whop) | YouTube-only, no compliance layer |
| [rushindrasinha/youtube-shorts-pipeline](https://github.com/rushindrasinha/youtube-shorts-pipeline) | Generation → captions → upload pipeline; multi-platform planned | Generation-focused, not clipping |

**Finding:** YouTube-side automation via the official Data API is a
solved problem. TikTok-side open-source posting is thinner and often
relies on unofficial routes — reinforcing the brief's decision to use the
official Content Posting API or fall back to a manual posting queue.
No project tracks submissions against Whop balance/approval states;
that tracker is ours to build.

## Revised build-vs-reuse recommendation

1. **Reuse/adapt:** `clipsai` / `AI-Youtube-Shorts-Generator` for
   rendering; chat-spike reference implementations for detection;
   `python-youtube-automator` pattern for YouTube upload.
2. **Audit before building:** `whopsdk-python` + Whop docs — may
   eliminate the scraping risk in Phase 1.
3. **Build (differentiators):** campaign EV scoring and alerting, rules
   parser + per-campaign compliance templates, compliance gate, Whop
   submission/earnings tracker. These have no prior art and are where the
   margin is.
