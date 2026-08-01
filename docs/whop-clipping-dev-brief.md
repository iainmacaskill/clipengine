# Development Brief: Whop Content Rewards Clipping Pipeline

*Status: Draft v1 — August 2026*
*Companion research: [research-twitch-clipping-revenue.md](research-twitch-clipping-revenue.md)*

## 1. Background

Whop Content Rewards is currently the dominant marketplace for paid stream
clipping: brands and streamers fund campaign budgets and pay clippers
**$0.20–$6 per 1,000 verified views** (average ~$1) for short vertical clips
posted to TikTok, YouTube Shorts, Instagram Reels and X. The platform pays
out ~$40,000/day across ~480,000 clippers, with campaigns from Polymarket,
ElevenLabs, MrBeast (Feastables) and streamers like Neon ($300k+/year paid
to clippers).

The economics reward **throughput of compliant, well-hooked clips submitted
early against campaigns with remaining budget**. That is a systems problem,
not an editing problem — which is what this team will build for.

## 2. Objective

Build a semi-automated pipeline that lets a small operator (initially one
person) participate in Whop Content Rewards campaigns at 5–10× the clip
throughput of manual work, while staying fully compliant with campaign
rules and platform terms of service.

Target outcome for v1: **20+ compliant clips/day across 2–3 active
campaigns, with rejection rate under 15%**, and full visibility of
earnings per clip/campaign/platform.

## 3. What we are building (scope)

### Phase 1 — Campaign intelligence (week 1–2)

The highest-leverage, lowest-risk component. Campaign selection beats
editing skill.

- **Campaign monitor**: poll the Content Rewards discover feed for active
  campaigns; capture CPM, total budget, *remaining* budget, content type
  (clipping vs UGC), allowed platforms, category, and rules text.
- **Scoring model**: rank campaigns by expected value — CPM × remaining
  budget × source-material familiarity × rule complexity (simple rules =
  fewer rejections). Alert (e.g. Discord/Telegram webhook) when a
  high-score campaign launches, since budget pools are first-come-first-served.
- **Rules parser**: extract structured requirements from campaign briefs
  (required hashtags, credits, banned edit styles, source links) into a
  checklist the pipeline enforces downstream.
- Storage: SQLite (consistent with this repo's tracker pattern).

### Phase 2 — Clip production pipeline (week 2–5)

- **Ingest**: download campaign source material (the brand's provided
  assets or the streamer's VOD where the campaign authorises it). Support
  Twitch/Kick VODs and YouTube sources via yt-dlp.
- **Highlight detection**: candidate-moment detection using chat-activity
  spikes (Twitch chat replay), audio energy/laughter detection, and a
  local LLM pass over the transcript (Whisper) to score "hook strength" of
  the first 2 seconds. This mirrors the local-LLM approach used elsewhere
  in this repo.
- **Edit/render**: ffmpeg-based template renderer — 9:16 crop with
  speaker tracking, burned-in animated captions (most viewing is muted),
  campaign-mandated credits/watermarks, 1080p output. Templates are
  per-campaign so rule compliance is baked into the render, not left to
  the operator.
- **Compliance gate**: automated pre-flight check of every rendered clip
  against the Phase 1 rules checklist (hashtags present, credit overlay
  present, duration in range, correct source). Nothing exports without a
  pass. Every rejected clip is unpaid work.

### Phase 3 — Posting, submission and tracking (week 5–8)

- **Posting assistant**: prepare per-platform upload bundles (video,
  caption with required hashtags, cover frame). Use official APIs where
  they exist (TikTok Content Posting API, YouTube Data API); otherwise
  generate a "ready to post" queue for manual upload — do **not** build
  unofficial automation that violates platform ToS.
- **Submission tracker**: record every Whop submission (campaign, post
  URL, timestamp) and reconcile against Whop balance: pending → approved
  (48h auto-approval window) → paid, plus rejection reasons.
- **Earnings dashboard**: per-clip and per-campaign revenue, views,
  effective CPM, rejection rate, and time-to-approval. This closes the
  loop for the Phase 1 scoring model (which campaigns/hook styles actually
  pay).

## 4. Explicitly out of scope

- **Any view manipulation.** Whop has bot detection, a 24-hour payout
  delay, and issues lifetime bans. Nothing in this system may buy,
  exchange, or simulate views. This is a hard line.
- **Scraping or automating Whop itself beyond read-only campaign
  discovery.** Submissions are made through the normal Whop flow; if Whop
  ships a public API we adopt it, otherwise submission stays manual with
  our tracker recording it.
- **Unauthorised clipping.** The pipeline only ingests source material a
  campaign explicitly authorises. No freelance clipping of streamers who
  haven't opted in — that's the copyright exposure documented in the
  research doc.
- **Mass fake accounts.** Multiple *legitimate* posting accounts per
  platform are normal practice; account farming/evasion is not.

## 5. Technical notes

- Language: Python, matching this repo (SQLite tracker, local LLM via
  `local_llm.py` pattern, small CLI entry points).
- Key dependencies: yt-dlp, ffmpeg, faster-whisper, existing local-LLM
  stack. TikTok/YouTube official API clients in Phase 3.
- Whop has no public Content Rewards API as of writing — Phase 1 discovery
  must be built defensively (feed structure will change) and degrade to
  manual entry.
- All secrets (platform tokens) via env/settings, never committed —
  follow `settings.py` conventions.

## 6. Milestones and success metrics

| Milestone | Target | Metric |
|---|---|---|
| M1 (end wk 2) | Campaign monitor + scoring live | Alerts within 15 min of campaign launch; 10+ campaigns tracked |
| M2 (end wk 5) | End-to-end clip from VOD to compliant export | <20 min operator time per clip; compliance gate passes 100% of exports |
| M3 (end wk 8) | Full loop with earnings dashboard | 20+ clips/day capacity; rejection rate <15%; per-clip P&L visible |
| M4 (wk 9+) | Optimisation loop | Hook-score model retrained on actual view data; effective CPM trending up |

Business success = **payout per operator-hour**, not clip volume. Track it
from M2 onward.

## 7. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Whop changes discover feed / adds API | High | Defensive parsing, manual-entry fallback; adopt official API if shipped |
| Campaign budget exhausts before approval | Medium | Alerting speed (M1 target), prefer campaigns with large remaining budgets |
| Brand-side rejection after views delivered | Medium | Compliance gate; favour campaigns with simple rules; track per-brand rejection history in scoring |
| Platform ToS action on posting accounts | Medium | Official APIs only; no automation of unofficial surfaces; per-account rate limits |
| TikTok/YouTube monetisation policy shifts | Low (campaign model doesn't depend on it) | Revenue is from Whop CPM, not platform creator funds |
| Rate compression as clipping saturates | Medium | Scoring model keeps us in the highest-EV campaigns; dashboard shows when to exit |

## 8. Open questions for the team

1. Do we target a single niche first (e.g. one streamer's campaigns) to
   tune the hook-detection model, or stay campaign-agnostic from day one?
2. Build vs buy for highlight detection — evaluate Eklipse/Opus Clip APIs
   as a Phase 2 shortcut before committing to in-house detection.
3. How many posting accounts per platform at launch, and who owns them
   operationally?
4. Threshold for adding UGC campaigns (original content, higher CPM,
   different production pipeline) — v2 or never?
