"""Campaign intelligence for Whop Content Rewards (dev brief Phase 1).

Campaign selection beats editing skill: this package discovers paid clipping
campaigns, scores them by expected value, parses their rules into an
enforceable checklist, and alerts when a high-value campaign launches.

Whop access is strictly read-only discovery (dev brief §4) — submissions and
everything else stay in the normal Whop web flow.
"""
