"""Whop submission tracker: pending -> approved (48h window) -> paid.

Submitting to Whop has no public API — it stays a manual web flow (dev brief
§4) and this tracker records what happened: every submission (campaign, post
URL, timestamp), the brand's verdict, and the money. Whop auto-approves
submissions the brand doesn't reject within 48 hours, so ``auto_approve``
advances pending records past that window; rejections need a reason so the
per-brand rejection history can feed campaign scoring (brief §7).

Lives in the campaigns DB alongside the campaign store — earnings roll up
per campaign for the dashboard and close the loop to Phase 1 scoring.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ..db import SqliteStore, utc_now
from .models import REWARD_CPM, Campaign

STATUSES = ("pending", "approved", "rejected", "paid")
AUTO_APPROVAL_HOURS = 48.0
REJECTION_RATE_TARGET = 0.15  # brief M3: rejection rate under 15%

_SCHEMA = """
CREATE TABLE IF NOT EXISTS submissions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id      TEXT NOT NULL,
    post_url         TEXT NOT NULL,
    platform         TEXT NOT NULL DEFAULT '',
    account          TEXT NOT NULL DEFAULT '',
    title            TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending','approved','rejected','paid')),
    submitted_at     TEXT NOT NULL,
    approved_at      TEXT,
    rejected_at      TEXT,
    paid_at          TEXT,
    rejection_reason TEXT NOT NULL DEFAULT '',
    views            INTEGER NOT NULL DEFAULT 0,
    amount           REAL NOT NULL DEFAULT 0,
    notes            TEXT NOT NULL DEFAULT '',
    UNIQUE (campaign_id, post_url)
);
"""


@dataclass
class Submission:
    id: int
    campaign_id: str
    post_url: str
    platform: str
    account: str
    title: str
    status: str
    submitted_at: str
    approved_at: str | None
    rejected_at: str | None
    paid_at: str | None
    rejection_reason: str
    views: int
    amount: float
    notes: str


@dataclass
class CampaignEarnings:
    campaign_id: str
    total: int = 0
    pending: int = 0
    approved: int = 0
    rejected: int = 0
    paid: int = 0
    paid_amount: float = 0.0
    expected_amount: float = 0.0  # EV of pending+approved, from campaign terms
    views: int = 0
    avg_hours_to_approval: float | None = None

    @property
    def rejection_rate(self) -> float | None:
        """Rejected share of resolved submissions; None until something resolves."""
        resolved = self.approved + self.rejected + self.paid
        return self.rejected / resolved if resolved else None

    @property
    def effective_cpm(self) -> float | None:
        """Actual payout per 1,000 views across paid submissions."""
        return self.paid_amount / self.views * 1000 if self.views and self.paid_amount else None


def expected_amount(sub: Submission, campaign: Campaign | None) -> float:
    """What this submission should pay if approved, from the campaign's terms."""
    if campaign is None:
        return 0.0
    if campaign.reward_model == REWARD_CPM:
        return sub.views / 1000.0 * campaign.reward_amount
    return campaign.reward_amount


class SubmissionStore(SqliteStore):
    SCHEMA = _SCHEMA

    def add(
        self,
        campaign_id: str,
        post_url: str,
        platform: str = "",
        account: str = "",
        title: str = "",
        at: str | None = None,
    ) -> Submission:
        post_url = post_url.strip()
        if not post_url:
            raise ValueError("post URL required - the tracker records real submissions")
        try:
            cur = self._conn.execute(
                """INSERT INTO submissions
                   (campaign_id, post_url, platform, account, title, submitted_at)
                   VALUES (?,?,?,?,?,?)""",
                (campaign_id, post_url, platform, account, title, at or utc_now()),
            )
        except sqlite3.IntegrityError:
            raise ValueError(
                f"already tracked: {post_url} was submitted to {campaign_id}"
            ) from None
        self._conn.commit()
        return self.get(cur.lastrowid)

    def get(self, sub_id: int) -> Submission:
        row = self._conn.execute(
            "SELECT * FROM submissions WHERE id=?", (sub_id,)
        ).fetchone()
        if row is None:
            raise LookupError(f"no submission #{sub_id}")
        return Submission(**dict(row))

    def list(
        self, status: str | None = None, campaign_id: str | None = None
    ) -> list[Submission]:
        query, params = "SELECT * FROM submissions", []
        clauses = []
        if status:
            clauses.append("status=?")
            params.append(status)
        if campaign_id:
            clauses.append("campaign_id=?")
            params.append(campaign_id)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        rows = self._conn.execute(query + " ORDER BY id", params).fetchall()
        return [Submission(**dict(r)) for r in rows]

    def approve(self, sub_id: int, at: str | None = None) -> Submission:
        sub = self.get(sub_id)
        if sub.status != "pending":
            raise ValueError(f"#{sub_id} is {sub.status}, only pending can be approved")
        self._conn.execute(
            "UPDATE submissions SET status='approved', approved_at=? WHERE id=?",
            (at or utc_now(), sub_id),
        )
        self._conn.commit()
        return self.get(sub_id)

    def reject(self, sub_id: int, reason: str, at: str | None = None) -> Submission:
        """Reason is mandatory - rejection history feeds campaign scoring."""
        if not reason.strip():
            raise ValueError("rejection reason required")
        sub = self.get(sub_id)
        if sub.status not in ("pending", "approved"):
            raise ValueError(f"#{sub_id} is {sub.status}, cannot reject")
        self._conn.execute(
            "UPDATE submissions SET status='rejected', rejected_at=?, "
            "rejection_reason=? WHERE id=?",
            (at or utc_now(), reason.strip(), sub_id),
        )
        self._conn.commit()
        return self.get(sub_id)

    def mark_paid(
        self, sub_id: int, amount: float, at: str | None = None
    ) -> Submission:
        """Record the actual payout. A pending submission is approved implicitly
        (payment proves approval; Whop pays 24h after approval)."""
        if amount <= 0:
            raise ValueError("paid amount must be positive")
        sub = self.get(sub_id)
        if sub.status == "rejected":
            raise ValueError(f"#{sub_id} was rejected, cannot mark paid")
        at = at or utc_now()
        self._conn.execute(
            "UPDATE submissions SET status='paid', paid_at=?, amount=?, "
            "approved_at=COALESCE(approved_at, ?) WHERE id=?",
            (at, amount, at, sub_id),
        )
        self._conn.commit()
        return self.get(sub_id)

    def set_views(self, sub_id: int, views: int) -> Submission:
        if views < 0:
            raise ValueError("views must be >= 0")
        self.get(sub_id)
        self._conn.execute(
            "UPDATE submissions SET views=? WHERE id=?", (views, sub_id)
        )
        self._conn.commit()
        return self.get(sub_id)

    def auto_approve(
        self, now: str | None = None, window_h: float = AUTO_APPROVAL_HOURS
    ) -> list[Submission]:
        """Advance pending submissions past Whop's 48h auto-approval window."""
        now_dt = (
            datetime.fromisoformat(now) if now else datetime.now(timezone.utc)
        )
        moved = []
        for sub in self.list(status="pending"):
            submitted = datetime.fromisoformat(sub.submitted_at)
            if now_dt - submitted >= timedelta(hours=window_h):
                approved_at = (submitted + timedelta(hours=window_h)).isoformat(
                    timespec="seconds"
                )
                self._conn.execute(
                    "UPDATE submissions SET status='approved', approved_at=?, "
                    "notes=CASE WHEN notes='' THEN ? ELSE notes || char(10) || ? END "
                    "WHERE id=?",
                    (approved_at, "auto-approved (48h window elapsed)",
                     "auto-approved (48h window elapsed)", sub.id),
                )
                moved.append(self.get(sub.id))
        self._conn.commit()
        return moved

    def earnings(
        self, campaigns: dict[str, Campaign] | None = None
    ) -> list[CampaignEarnings]:
        """Per-campaign rollup for the dashboard, ordered by paid amount."""
        campaigns = campaigns or {}
        rollup: dict[str, CampaignEarnings] = {}
        approval_hours: dict[str, list[float]] = {}
        for sub in self.list():
            e = rollup.setdefault(sub.campaign_id, CampaignEarnings(sub.campaign_id))
            e.total += 1
            if sub.status == "pending":
                e.pending += 1
            elif sub.status == "approved":
                e.approved += 1
            elif sub.status == "rejected":
                e.rejected += 1
            elif sub.status == "paid":
                e.paid += 1
            e.views += sub.views
            if sub.status == "paid":
                e.paid_amount += sub.amount
            elif sub.status in ("pending", "approved"):
                e.expected_amount += expected_amount(
                    sub, campaigns.get(sub.campaign_id)
                )
            if sub.approved_at:
                delta = datetime.fromisoformat(sub.approved_at) - datetime.fromisoformat(
                    sub.submitted_at
                )
                approval_hours.setdefault(sub.campaign_id, []).append(
                    delta.total_seconds() / 3600.0
                )
        for cid, hours in approval_hours.items():
            rollup[cid].avg_hours_to_approval = sum(hours) / len(hours)
        return sorted(rollup.values(), key=lambda e: e.paid_amount, reverse=True)
