# Audit: whopsdk-python — Content Rewards API Surface

*Audit date: August 2026 · SDK version 0.0.41 (last commit 2026-07-20)*
*Companion docs: [dev brief](whop-clipping-dev-brief.md) · [prior art](whop-clipping-prior-art.md)*

Audit of [whopio/whopsdk-python](https://github.com/whopio/whopsdk-python)
(official SDK, Stainless-generated from Whop's OpenAPI spec, actively
maintained) to answer the open question from the prior-art survey: **is
Content Rewards campaign data exposed via the official API?**

## Verdict

**Partially.** There is no resource named Content Rewards and no
CPM-per-verified-views campaign surface — but Whop's **Workforce
Bounties** API explicitly models clipping work and gives us most of what
Phase 1 of the brief needs, read-only, through a supported SDK. The
per-1,000-views product does not appear in the public API, so the brief's
defensive-discovery fallback still applies to those campaigns only.

## What exists

### Workforce Bounties (`client.workforce.bounties`, `client.bounties`)

- `GET /workforce/bounties` (list, cursor-paginated) and
  `GET /workforce/bounties/{id}` — read-only discovery.
- `POST /bounties` — create (the brand side).
- The model has a `business_goal_type` enum that includes **`"clipping"`**
  and **`"ugc_content"`** — Whop's own taxonomy for this work.
- Economics fields map directly onto the brief's campaign scoring:
  `budget_amount` (total pool), `gross_reward_amount` (per accepted
  submission), `accepted_submissions_limit`, `spots_remaining`,
  `gross_paid_out_amount`, `unresolved_submissions_count`, and a
  `status` lifecycle (`scheduled/open/closed/completed/canceled`).
- List filters: `status`, `account_id`, created-date window, title
  substring `query`, sort by `created_at` or `gross_paid_out_amount`.
  **No server-side filter on `business_goal_type`** — filter client-side
  after fetching.
- Payment model is **fixed reward per accepted submission**, not CPM. So
  bounty-style clipping gigs are fully visible; the flagship
  $X-per-1,000-views campaigns are a different product.
- **No submission endpoints** — you cannot submit work to a bounty via
  the API; only aggregate submission counts are readable. Submission
  remains a manual/web flow, as the brief assumed.

### Social Accounts (`client.social_accounts`)

- Connect/list/delete accounts on **x, instagram, youtube, tiktok,
  facebook**, plus `GET /social_accounts/{id}/posts`.
- This is the connected-posting-account model Content Rewards uses for
  view verification, exposed via API — useful for our submission tracker,
  though the post types carry ad-oriented CTA fields, suggesting the
  endpoint primarily serves Whop's ads product.

### Adjacent but not Content Rewards

- `ad_campaigns` / `ads` / `ad_reports` have `cost_per_mille` fields, but
  this is **Whop's paid-ads product** (spend per 1,000 impressions on
  Whop), not clipper campaigns. Don't confuse the two.
- `payouts`, `withdrawals`, `ledger_accounts`, `transfers` cover the
  balance/earnings side for the dashboard's reconciliation step.

## What does not exist

- No `content_rewards` resource, no per-view reward rate, no campaign
  rules/brief field, no allowed-platforms field, no clip submission or
  approval endpoints, no view-verification API.

## Impact on the dev brief

1. **Phase 1 upgrade:** build campaign discovery on
   `workforce.bounties.list(status="open")` + client-side
   `business_goal_type in ("clipping", "ugc_content")` filtering. This is
   a supported, stable integration — no scraping for bounty-model
   campaigns. EV scoring inputs (`budget_amount`, `spots_remaining`,
   `gross_reward_amount`) come straight from the model.
2. **Defensive discovery still needed** for CPM-per-views Content Rewards
   campaigns, which remain app/web-only. Keep the manual-entry fallback.
3. **Phase 3 unchanged:** submissions stay manual (no API); the tracker
   reconciles via the payouts/ledger endpoints where possible.
4. **Auth note:** the API requires a Whop API key; `user_id`-scoped
   listing only works for the authenticated user, and `account_id`
   scoping requires read access to that account.

## Addendum — first production sync (2026-08-01)

The live API **404s `GET /api/v1/workforce/bounties`** ("Unrecognized request
URL") with a valid key: the workforce surface exists in the SDK (0.0.41, the
latest) but is not yet rolled out in production. The SDK's *top-level*
`client.bounties` resource (`GET /bounties`, `GET /bounties/{id}`) is the
original surface and the working fallback, with a different read model:

- `status`: `published`/`archived`/`scheduled` (vs `open`/`closed`/...)
- budget: `total_available` (remaining pool) + `total_paid` (paid out)
- `description` (rules text) is inline in the *list* response — no detail
  fetch needed
- **not exposed**: `business_goal_type`, `gross_reward_amount`,
  `spots_remaining`, funding account/poster — even though the create params
  accept them, the read serializer omits them, so client-side goal-type
  filtering is impossible on this surface and per-submission reward is
  unknown (the scorer treats unknown rate as neutral 1.0)

clipengine's client tries `/workforce/bounties` first and falls back to
`/bounties` on 404, translating the vocabulary — so it upgrades itself the
day Whop ships the workforce surface. Payouts/ledger endpoints have not yet
been probed against production.
