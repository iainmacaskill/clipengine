# Product Plan: ClipEngine — Automated Twitch-to-Shorts Clip Pipeline

**Status:** Draft v1 · **Date:** 2026-07-29 · **Owner:** Iain Macaskill

---

## 1. One-line pitch

An automated pipeline that ingests Twitch streams from popular gamers, detects highlight
moments with AI, edits them into vertical short-form video optimised for TikTok and
YouTube Shorts, and publishes them at scale on our own network of clip channels — keeping 100% of
creator-reward revenue, with streamer permission obtained through a free opt-in
(promotion-for-permission) flow rather than paid licensing deals.

---

## 2. The critical constraint that shapes the whole product

Before anything else: **the naive version of this business does not work**, and the plan
below is structured around fixing that.

1. **Copyright.** A Twitch VOD/broadcast is the streamer's copyrighted content (and often
   contains the game publisher's content under a separate licence). Reposting clips
   without permission is infringement; channels doing this get DMCA strikes and
   terminated.
2. **Monetisation eligibility.** Both reward programmes explicitly exclude unoriginal
   content:
   - **TikTok Creator Rewards Program** requires *original* content, ≥1 minute duration,
     10k followers, and 100k valid views in the trailing 30 days. Reposted/unoriginal
     content earns nothing and risks the account.
   - **YouTube Partner Program (Shorts)** applies the "reused content" policy — clips of
     someone else's stream without significant original transformation are demonetised.
     Threshold: 1k subscribers + 10M Shorts views in 90 days (or 4k long-form watch
     hours).
3. **Detection is automated.** Both platforms fingerprint content (Content ID, TikTok's
   matching systems). "Fly under the radar" is not a strategy; it is a countdown timer.

**A note on "streamers are happy to be clipped."** Largely true — clip channels are
free marketing and many streamers encourage them. But two distinctions matter for a
commercial automated operation:

- *Tolerance is not a licence, and it flips when money appears.* Streamers tolerate fan
  clipping; several large streamers have DMCA'd clip farms specifically once those
  channels were visibly monetising at scale. Informal goodwill is a single point of
  failure — one takedown wave can kill a channel carrying hundreds of videos. The fix is
  nearly free: a **one-click opt-in consent** (streamer grants blanket clip permission in
  exchange for credit + links, no revenue share). We keep 100% of revenue; the only
  difference is written permission instead of assumed permission.
- *Permission does not unlock the reward programmes.* TikTok and YouTube's originality
  rules apply regardless of whether the source creator is happy: content the poster
  didn't create, without significant creative input, is ineligible for Creator Rewards
  and falls under YouTube's reused-content policy even with a licence in hand. What
  unlocks monetisation is **transformation** — real editing, captions, hooks, framing,
  compilation/commentary formats — which our pipeline produces anyway. YouTube clip
  channels with genuine editorial value do get monetised; TikTok Creator Rewards is the
  stricter programme and should be modelled as reach + upside, not the base revenue case.

The viable models:

| Model | Description | Who earns the rewards |
|---|---|---|
| **C. Own-brand permissioned clip network (primary)** | We operate our own clip channels. Sources limited to streamers with published clip-permission policies or our one-click opt-in. Heavy automated transformation for originality. No revenue share. | **Us — 100%** |
| **A. Streamer-as-customer (SaaS)** | Streamers run ClipEngine on their own streams, posting to their own accounts. Fully rewards-eligible originality. | The streamer; we charge SaaS fees |
| **B. Licensed clip network (rev-share)** | Fallback for high-value streamers who won't grant free permission: written licence + revenue share. | Us, sharing back |
| ~~D. Unlicensed raw reposting~~ | Scrape and repost without permission or transformation. | ❌ Demonetised by originality rules regardless of copyright posture; account bans. **Out of scope.** |

**Recommendation: lead with Model C** — it matches the goal of keeping all clip revenue
and requires no commercial negotiation, only a free consent flow. Run Model A (SaaS) in
parallel as a second revenue line with zero platform-policy risk and use it as the
carrot in the opt-in pitch ("let us clip you free on our network, or subscribe and we
clip to *your* accounts"). Model B is reserved for must-have streamers. The same
pipeline powers all three.

---

## 3. Market and opportunity

- **Supply:** Top Twitch streamers produce 4–10 hours of raw content per day; almost all
  of it is under-exploited on short-form platforms. Manually clipping costs $500–3,000/mo
  per streamer (human editors), which only the top ~1% can justify.
- **Demand:** Short-form is the discovery engine for streamers — clips drive new Twitch
  follows and sponsorship value. Mid-tier streamers (1k–50k CCV… roughly 5k–500k
  followers) want this but can't afford editors.
- **Comparable products:** Opus Clip, Eklipse.gg, Momento, StreamLadder. Eklipse is the
  closest comparator (Twitch-focused, freemium). Differentiation targets: (a) better
  highlight detection using chat + game events, not just audio; (b) fully hands-off
  auto-publish with per-platform optimisation; (c) rewards/earnings analytics so the
  streamer sees ROI in currency, not views.
- **Revenue benchmarks for modelling** (order-of-magnitude, volatile):
  - TikTok Creator Rewards: ~$0.40–$1.00 RPM on qualified views (>1 min videos only).
  - YouTube Shorts: ~$0.10–$0.30 RPM.
  - Implication: a channel doing 10M qualified views/month spans roughly $1k–$10k/month.
    Rewards alone are thin margins — which further supports SaaS pricing (Model A) as the
    primary revenue line, with rewards share as upside.

---

## 4. Product overview

### 4.1 Product surfaces

**Model C (primary) — internal operations console.** Our own team's dashboard:

1. Roster management: streamers we're cleared to clip (published clip-policy links or
   signed opt-ins on file, verified per source before ingestion is enabled).
2. Channel portfolio: our TikTok/Shorts accounts, each themed by game or streamer
   cluster, with per-channel posting cadence and monetisation status.
3. Candidate review queue → approve/auto-publish, plus originality-strength indicators
   (how much transformation was applied) per clip.
4. Earnings dashboard: rewards revenue per channel/streamer/clip-type, feeding the
   learning loop.

**Opt-in consent flow (public-facing, minimal).** A one-page form a streamer (or their
mod/manager) completes in under a minute: grant blanket clip permission, choose credit
format, optional exclusions (e.g. no sponsor segments). Stored with timestamp as our
permission record. The pitch to streamers: free promotion, credited links, zero effort.

**Model A (secondary) — streamer SaaS dashboard.** A web dashboard where a streamer:

1. Connects Twitch (OAuth) + TikTok + YouTube accounts.
2. Sets preferences: games, clip style, caption style, branding overlay, posting cadence,
   auto-publish vs. review queue.
3. Receives clips: pipeline watches their streams/VODs, generates candidate clips ranked
   by predicted performance, and either auto-publishes or queues for one-tap approval.
4. Sees analytics: views, follower growth, estimated rewards earnings per platform, and
   which clip *types* perform (feedback loop into detection).

### 4.2 The pipeline (the core asset)

```
┌────────────┐  ┌──────────────┐  ┌────────────┐  ┌─────────────┐  ┌───────────┐
│ INGEST     │→ │ DETECT       │→ │ EDIT       │→ │ PACKAGE     │→ │ PUBLISH   │
│ VOD/live   │  │ highlights   │  │ cut+crop   │  │ captions,   │  │ TikTok /  │
│ + chat log │  │ multi-signal │  │ vertical   │  │ hook, title │  │ Shorts    │
└────────────┘  └──────────────┘  └────────────┘  └─────────────┘  └─────┬─────┘
                                                                        │
                                          ┌─────────────────────────────▼──────┐
                                          │ ANALYTICS + LEARNING LOOP          │
                                          │ per-clip performance → detector    │
                                          └────────────────────────────────────┘
```

**Stage 1 — Ingest**
- Twitch Helix API + authorised VOD access (streamer OAuth grants VOD download rights).
  Live-mode later: ingest the stream in near-real-time so clips post while the stream is
  still trending.
- Capture the **chat log with timestamps** — this is the highest-value cheap signal.
- Store raw segments in object storage; retain only a rolling window (cost control).

**Stage 2 — Highlight detection (multi-signal scoring)**
Score the timeline in sliding windows using an ensemble:

| Signal | Method | Cost |
|---|---|---|
| Chat velocity + emote spikes (LUL, PogChamp, KEKW clusters) | Time-series spike detection over chat log | Very low |
| Audio excitement (shouting, laughter, sudden silence) | Audio energy + laughter classifier | Low |
| Streamer speech content | Whisper ASR → local/LLM scoring of "clip-worthiness" (jokes, rage, hype callouts) | Medium |
| Game events (kills, clutches, wins) | CV detection of killfeeds/victory screens per supported game; start with 3–5 top games | Medium |
| Twitch native clip creation rate | Viewers clipping = ground truth interest | Very low |

Fuse into a single score; take top-N non-overlapping windows per stream. **Key design
decision:** chat + audio alone get ~80% of the value at ~5% of the compute cost of
frame-level vision. Ship that first; add game-event CV per title later.

**Stage 3 — Edit**
- Boundary refinement: snap cut points to sentence boundaries (from ASR) and
  action boundaries, with a pre-roll to preserve context/setup.
- Vertical reformat (9:16): detect facecam region → facecam top, gameplay bottom (the
  dominant layout meta), or smart-crop gameplay when no facecam. FFmpeg-based, GPU where
  available.
- Duration targeting: **default 61–90 seconds** — this is not aesthetic, it's economic:
  TikTok Creator Rewards only pays on videos over 1 minute. Sub-60s variants only for
  pure-reach posts.

**Stage 4 — Package**
- Burned-in animated captions (word-level Whisper timestamps) — captions are
  table-stakes for short-form retention.
- Hook engineering: first 1.5s gets a text hook ("he did NOT expect this…") generated by
  LLM from the transcript; thumbnails for Shorts.
- Metadata per platform: title, hashtags, sounds-safe check (mute/replace copyrighted
  music segments — critical, background Spotify is the #1 DMCA cause in stream VODs).
- Streamer branding overlay + "follow on Twitch" end-card (this is the value prop that
  makes streamers pay).

**Stage 5 — Publish**
- TikTok Content Posting API (requires audited app approval — long lead time, start
  early) and YouTube Data API `videos.insert`.
- Scheduling engine: per-platform optimal posting windows, spacing rules, per-account
  daily caps (platforms throttle/flag bulk posting).
- Review queue mode (default for new accounts) vs. full auto.

**Stage 6 — Analytics + learning loop**
- Pull per-video stats via platform APIs; join with clip features (signal scores, game,
  duration, hook type).
- Retrain/reweight the detector per streamer — each audience has its own taste. This
  compounding per-customer model quality is the long-term moat.

---

## 5. Architecture & stack (proposed)

- **Orchestration:** queue-based workers (Celery/RQ or Temporal); each pipeline stage a
  worker type; horizontal scale on GPU stages only.
- **Media:** FFmpeg; PySceneDetect; Whisper (faster-whisper on GPU) for ASR; small
  audio classifiers (laughter/excitement); YOLO-class detector for facecam/killfeed.
- **LLM usage:** clip-worthiness scoring, hooks, titles, hashtags. Latency-insensitive →
  batch calls; small local models for high-volume scoring, frontier model (Claude) for
  final packaging copy on top-ranked clips only.
- **App:** FastAPI backend + simple React dashboard; Postgres (clips, scores, schedules,
  earnings); S3-compatible object storage with lifecycle deletion.
- **Cost model target:** < $0.15 fully-loaded compute per published clip (ASR is the
  dominant cost; chat-gated processing keeps us from transcribing 8h of silence).

---

## 6. MVP scope (Phase 1)

**Goal: prove the pipeline produces clips that earn views, running 2–3 of our own
channels sourced from 10–20 opted-in / clip-permissive streamers, in 6–8 weeks.**

In scope:
- Opt-in consent form + roster of streamers with verified clip permission (start with
  streamers who already publish permissive clip policies — fastest to onboard).
- VOD-based (not live) ingestion.
- Detection: chat velocity + audio excitement + Twitch clip-rate signals only.
- Facecam-top/gameplay-bottom vertical edit, word-level captions, 61–90s targeting,
  credit overlay + linked attribution per the streamer's chosen format.
- Review queue with human approval on every clip (quality bar + originality check);
  **YouTube Shorts auto-publish only** (TikTok API audit will still be pending; MVP
  exports TikTok-ready files for manual upload).
- 2–3 own-brand channels themed by game, growing toward monetisation thresholds
  (YouTube: 1k subs + 10M Shorts views/90d; TikTok: 10k followers + 100k views/30d).

Explicitly out of scope for MVP: live ingestion, game-event CV, TikTok auto-post,
earnings analytics, the Model A SaaS dashboard.

**MVP success criteria:** ≥15 streamers on the permission roster; channels on a
trajectory to hit monetisation thresholds within 90 days; ≥50% of candidate clips
passing human review; zero takedowns or originality flags.

## 7. Roadmap after MVP

- **Phase 2 (months 3–4): Monetise & measure.** TikTok Content Posting API (submit
  audit in week 1 of MVP), scheduling engine, analytics ingestion, earnings tracking per
  channel/clip-type, per-audience detector tuning. First channels cross monetisation
  thresholds; apply to both reward programmes.
- **Phase 3 (months 5–6): Scale the network.** Grow the permission roster (target 100+
  streamers), spin up channels per game vertical, live-mode clipping (post within
  minutes of the moment), game-event CV for top 5 titles, A/B hooks, multi-language
  caption translation (huge cheap reach multiplier). Compilation/commentary long-form
  formats for YouTube — stronger originality posture *and* higher RPM than Shorts.
- **Phase 4 (months 6+): Model A SaaS.** Package the same pipeline as a streamer-facing
  product (£49–£199/mo tiers); use the opt-in roster as the warm lead list. Model B
  rev-share licences only for must-have streamers who decline the free opt-in.

---

## 8. Business model & unit economics

- **Primary revenue: creator rewards on our own channels (Model C), 100% retained.**
  No revenue share — permission is obtained free via the opt-in flow.
- **Secondary (Phase 4): SaaS** tiers by clip volume and features, target £99/mo
  average; plus Model B rev-share on the rare negotiated licences.
- **Illustrative Model C economics per channel:** ~90 clips/mo × $0.15 compute ≈
  $13.50 COGS. Revenue is view-dependent: at 3M qualified monthly views a channel earns
  roughly $300–$900/mo on YouTube Shorts RPMs ($0.10–0.30) or $1.2k–$3k/mo if TikTok
  Creator Rewards qualification holds ($0.40–1.00 RPM, >1min videos only). Compilation
  long-form on YouTube ($2–5+ RPM) is the highest-value slot per view.
- **Portfolio maths:** treat channels like positions — spin up cheaply, measure at 60/90
  days against threshold trajectories, kill underperformers monthly. Break-even per
  channel is low (~0.5M Shorts views/mo covers compute + ops share); the tail risk is
  not cost, it's monetisation review rejection — which is why originality strength is
  tracked per clip and why the SaaS line exists as the policy-risk-free hedge.

## 9. Key risks & mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Platform policy: content deemed unoriginal / rewards denied or clawed back | High | This is Model C's #1 risk. Maximise transformation on every clip (editing, captions, hooks, framing, compilations); track originality strength per clip; weight YouTube (clearer transformation precedent) over TikTok in revenue projections; Model A SaaS as the policy-risk-free hedge |
| Streamer goodwill flips once channels visibly earn (DMCA wave on a large channel) | High | Never ingest without a published clip policy or signed opt-in on file; prominent credit + links on every clip; honour revocation within 24h; keep the roster diversified so no streamer is >10% of a channel's content |
| Music DMCA inside gameplay/stream audio | High | Audio fingerprint check stage; auto-mute/replace music beds before publish |
| TikTok API audit rejection or posting caps | Medium | Apply early; review-queue + export fallback; diversify to Shorts + Instagram Reels |
| Detection quality below "streamer would post this" bar | Medium | Human-in-the-loop review queue from day 1; per-streamer learning loop |
| Platforms change RPM/thresholds (they do, often) | Medium | SaaS-first revenue; rewards treated as upside, never base case |
| Incumbents (Eklipse, Opus) | Medium | Differentiate on chat-signal detection quality, hands-off publishing, and earnings-denominated analytics |
| AI-content disclosure rules tighten | Low | Clips are human-created content, AI-edited; label where required |

## 10. KPIs

- **Pipeline quality:** candidate→approved rate (target >50% MVP, >75% by Phase 3);
  time-from-moment-to-published (VOD: <12h; live mode: <15min).
- **Customer value:** views per published clip vs. streamer's manual baseline; Twitch
  follower conversion from end-cards; churn <5%/mo.
- **Business:** MRR, gross margin (>85%), compute cost per published clip (<$0.15),
  Model B portfolio rewards RPM.

## 11. Immediate next steps

1. Build the source roster: compile 30–50 popular streamers who already publish
   permissive clip policies (fastest legitimate supply, zero negotiation); draft the
   one-click opt-in consent form and the promotion-for-permission pitch for the rest.
2. Have a lawyer sanity-check the opt-in consent wording once (one-off cost; it's the
   permission record the whole model rests on).
3. Submit TikTok developer app for Content Posting API audit (longest external lead
   time).
4. Technical spike (1 week): chat-spike + audio-energy detector against 3 public VODs;
   eyeball whether top-10 windows match the streamer's own posted clips.
5. Build MVP per §6 and launch the first 2 channels.
