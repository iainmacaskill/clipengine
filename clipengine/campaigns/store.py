"""SQLite campaign store: current state + append-only budget snapshots.

Every ``upsert`` also appends a snapshot per campaign, so the history table
shows budget depletion velocity over successive syncs — the signal for "get
in now or skip" on first-come-first-served pools. ``upsert`` returns the
campaigns not seen before, which drives launch alerts.

Timestamps are passed in by the caller (injectable for tests), matching the
analytics store pattern.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone

from .models import Campaign, Snapshot

_SCHEMA = """
CREATE TABLE IF NOT EXISTS campaigns (
    id               TEXT PRIMARY KEY,
    source           TEXT NOT NULL CHECK (source IN ('whop_bounty', 'manual')),
    title            TEXT NOT NULL,
    brand            TEXT NOT NULL DEFAULT '',
    goal_type        TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL,
    currency         TEXT NOT NULL DEFAULT 'usd',
    reward_model     TEXT NOT NULL CHECK (reward_model IN ('per_submission', 'cpm')),
    reward_amount    REAL NOT NULL,
    budget_total     REAL NOT NULL,
    budget_remaining REAL NOT NULL,
    spots_remaining  INTEGER,
    paid_out         REAL NOT NULL DEFAULT 0,
    unresolved       INTEGER NOT NULL DEFAULT 0,
    platforms        TEXT NOT NULL DEFAULT '[]',
    rules_text       TEXT NOT NULL DEFAULT '',
    url              TEXT NOT NULL DEFAULT '',
    created_at       TEXT NOT NULL DEFAULT '',
    first_seen       TEXT NOT NULL,
    last_seen        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS snapshots (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id      TEXT NOT NULL,
    at               TEXT NOT NULL,
    status           TEXT NOT NULL,
    budget_remaining REAL NOT NULL,
    spots_remaining  INTEGER,
    paid_out         REAL NOT NULL DEFAULT 0,
    unresolved       INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_snapshots_campaign ON snapshots (campaign_id, at);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class CampaignStore:
    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> CampaignStore:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def upsert(self, campaigns: list[Campaign], at: str | None = None) -> list[Campaign]:
        """Insert/update campaigns + append a snapshot each; returns the new ones.

        An update never blanks rules_text: a later shallow sync (rules fetch
        skipped or failed) keeps the rules captured earlier.
        """
        at = at or _now()
        new: list[Campaign] = []
        for c in campaigns:
            if self.get(c.id) is None:
                new.append(c)
            self._conn.execute(
                """INSERT INTO campaigns
                   (id, source, title, brand, goal_type, status, currency,
                    reward_model, reward_amount, budget_total, budget_remaining,
                    spots_remaining, paid_out, unresolved, platforms, rules_text,
                    url, created_at, first_seen, last_seen)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     title=excluded.title, brand=excluded.brand,
                     goal_type=excluded.goal_type, status=excluded.status,
                     currency=excluded.currency, reward_model=excluded.reward_model,
                     reward_amount=excluded.reward_amount,
                     budget_total=excluded.budget_total,
                     budget_remaining=excluded.budget_remaining,
                     spots_remaining=excluded.spots_remaining,
                     paid_out=excluded.paid_out, unresolved=excluded.unresolved,
                     platforms=excluded.platforms,
                     rules_text=CASE WHEN excluded.rules_text = ''
                                     THEN campaigns.rules_text
                                     ELSE excluded.rules_text END,
                     url=CASE WHEN excluded.url = '' THEN campaigns.url
                              ELSE excluded.url END,
                     created_at=excluded.created_at, last_seen=excluded.last_seen""",
                (c.id, c.source, c.title, c.brand, c.goal_type, c.status,
                 c.currency, c.reward_model, c.reward_amount, c.budget_total,
                 c.budget_remaining, c.spots_remaining, c.paid_out, c.unresolved,
                 json.dumps(c.platforms), c.rules_text, c.url, c.created_at,
                 at, at),
            )
            self._conn.execute(
                """INSERT INTO snapshots
                   (campaign_id, at, status, budget_remaining, spots_remaining,
                    paid_out, unresolved)
                   VALUES (?,?,?,?,?,?,?)""",
                (c.id, at, c.status, c.budget_remaining, c.spots_remaining,
                 c.paid_out, c.unresolved),
            )
        self._conn.commit()
        return new

    def get(self, campaign_id: str) -> Campaign | None:
        row = self._conn.execute(
            "SELECT * FROM campaigns WHERE id=?", (campaign_id,)
        ).fetchone()
        return _campaign(row) if row else None

    def list(self, status: str | None = None) -> list[Campaign]:
        query, params = "SELECT * FROM campaigns", ()
        if status:
            query += " WHERE status=?"
            params = (status,)
        rows = self._conn.execute(query + " ORDER BY first_seen DESC", params).fetchall()
        return [_campaign(r) for r in rows]

    def history(self, campaign_id: str) -> list[Snapshot]:
        rows = self._conn.execute(
            "SELECT * FROM snapshots WHERE campaign_id=? ORDER BY at, id",
            (campaign_id,),
        ).fetchall()
        return [
            Snapshot(
                campaign_id=r["campaign_id"], at=r["at"], status=r["status"],
                budget_remaining=r["budget_remaining"],
                spots_remaining=r["spots_remaining"],
                paid_out=r["paid_out"], unresolved=r["unresolved"],
            )
            for r in rows
        ]


def _campaign(row: sqlite3.Row) -> Campaign:
    d = dict(row)
    d.pop("first_seen", None)
    d.pop("last_seen", None)
    d["platforms"] = json.loads(d["platforms"] or "[]")
    return Campaign(**d)
