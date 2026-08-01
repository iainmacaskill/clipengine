"""Campaign dataclasses shared across discovery, storage, and scoring.

One normalised shape covers both campaign kinds:

- Whop Workforce Bounties (``source="whop_bounty"``): fixed reward per accepted
  submission, fully visible via the official API (see docs/whopsdk-python-audit.md).
- Manual entries (``source="manual"``): the flagship CPM-per-1,000-views Content
  Rewards campaigns, which have no public API and are keyed in by the operator.
"""
from __future__ import annotations

from dataclasses import dataclass, field

REWARD_PER_SUBMISSION = "per_submission"
REWARD_CPM = "cpm"  # reward_amount is per 1,000 verified views


@dataclass
class Campaign:
    id: str                 # "bnty_..." (Whop) or "manual:<slug>"
    source: str             # "whop_bounty" | "manual"
    title: str
    brand: str = ""         # funding account / poster
    goal_type: str = ""     # clipping | ugc_content | ...
    status: str = "open"    # scheduled | open | closed | completed | canceled
    currency: str = "usd"
    reward_model: str = REWARD_PER_SUBMISSION
    reward_amount: float = 0.0
    budget_total: float = 0.0
    budget_remaining: float = 0.0
    spots_remaining: int | None = None   # bounty winner slots; None for CPM
    paid_out: float = 0.0
    unresolved: int = 0                  # submissions awaiting an outcome
    platforms: list[str] = field(default_factory=list)
    rules_text: str = ""
    url: str = ""
    created_at: str = ""

    @property
    def open(self) -> bool:
        return self.status == "open"


@dataclass
class Snapshot:
    """Point-in-time budget state; the history shows depletion velocity."""

    campaign_id: str
    at: str
    status: str
    budget_remaining: float
    spots_remaining: int | None
    paid_out: float
    unresolved: int
