# Whop loop dress rehearsal — full cycle (2026-08-01)

Synthetic end-to-end run of the entire Whop Content Rewards loop in a sandboxed
environment: a local mock of the Whop API (endpoint shapes copied from
whop-sdk 0.0.41: cursor pagination, list-vs-detail field split, payouts,
ledger) plus the synthetic 360s VOD and chat log from the pipeline dress
rehearsal. `WHOP_BASE_URL` (mirroring the official SDK's env override) pointed
the real CLI at the mock — no code was stubbed; every stage ran the production
path over HTTP.

Mock campaign board: a clipping bounty ($40/submission, 50 spots, 9-item
rules text), a UGC bounty ($80/submission), a non-clipping `owned_account_growth`
bounty (should be filtered), a junk $1 bounty, and a draining budget pool.
A manual CPM campaign ($1.50/1k views) was keyed in alongside.

## Results by stage

| Stage | Result |
|---|---|
| campaigns sync (Phase 1) | 3/3 clipping+UGC bounties discovered over 2 pages of cursor pagination; growth bounty **correctly filtered client-side**; rules text fetched per bounty from the detail endpoint |
| scoring | Ranked with visible breakdowns; familiarity boost (1.2 for `valorant`/`neonplays`) and rule-simplicity discount both reflected in the numbers |
| launch alert | One Discord-format webhook on first sync with all new campaigns; **0 new → no alert** on re-syncs |
| budget snapshots | Depletion visible across syncs in `campaigns show` history (1800 → 1680 after the pool drained server-side) |
| rules parser | 9-item checklist from the bounty brief: hashtag, mention, 30–90s bounds, 2 platforms, 2 banned lines, source link |
| process --campaign (Phase 2) | 2/2 clips rendered under the template: merged credit burned (`clips: @neonplays` — **no duplication**, roster credit already carried the mandated mention), compliant caption `#NeonValorant @neonplays` generated, gate PASS + manual items recorded in the manifest |
| gate adversarial check | Same clip, `--platform instagram`: **FAIL on exactly the platform check**, all six other checks pass (real ffprobe duration 75s inside 30–90s) |
| queue | Gate-passing clips queued with the compliant caption as title, 30-min spacing respected |
| submissions (Phase 3) | pending → 48h auto-approve (backdated 50h; timestamped at window end, verify-on-Whop reminder printed) → paid with backfilled approval; rejection recorded with the brand's reason; duplicate URL+campaign refused |
| earnings dashboard | Per-campaign rollup correct: effective CPM 1.50/1k on the CPM campaign (exactly its stated rate), 3.33/1k derived on the bounty, 48h approval time on the auto-approved one, 50% rejection rate **flagged against the <15% target** |
| reconcile | Tracker totals vs mock Whop `/payouts` + `/ledger_accounts`: completed withdrawals counted, in-transit excluded, balance + pending shown |

## Findings

1. **`alert_min_score` default (3.0) is too permissive** — the junk $1/500-spot
   bounty scored 3.1 and made the launch alert. The score scale is dominated by
   the reward rate, so a flat threshold needs to be set per operator once real
   campaign data exists (something like 20+ would have kept only the two real
   campaigns). Config-only change; noted in the config comment.
2. **Score scale mixes reward models**: $80/submission bounties outscore
   $1.50/1k-views CPM campaigns (181 vs 8) because rate enters raw. The brief's
   "comparable units of work" assumption holds for ranking *within* a model but
   cross-model comparison should be read with care until real payout-per-hour
   data (M4) calibrates it.
3. **Auto-approval UX is right**: timestamping at window-end (not sync time)
   keeps time-to-approval honest (48h, not whenever cron ran), and the
   verify-on-Whop reminder covers the assumption that the brand didn't reject.
4. Two-page pagination, list/detail field split, and the no-server-side
   goal-type filter all behaved as the SDK audit predicted — the client-side
   handling is exercised, not just unit-tested.
5. `WHOP_BASE_URL` override (added for this rehearsal, mirroring the official
   SDK) doubles as the hook for staging/testing against any future Whop test
   environment.

## Not exercised (needs real credentials / production API)

Real Whop responses (field drift vs the SDK snapshot is the main risk — the
defensive-parsing requirement stands); real TikTok/YouTube publishes of the
queued clips; CPM campaign discovery (no public API — manual entry is the
designed path and was used here); actual payout timing against the 24h delay.

## Verdict

The full loop — discover → score → alert → produce under template → gate →
queue → submit (manual) → track → reconcile — runs end to end with no code
changes needed beyond the `WHOP_BASE_URL` override. First real-world step
remains: a production `campaigns sync` with a real API key to validate field
shapes, then cron the three sync commands (`campaigns sync`,
`submissions sync`, `stats sync`).
