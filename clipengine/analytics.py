"""Analytics: per-clip performance snapshots and reporting.

Closes the pipeline's loop (plan §4.2 stage 6): pull stats for every published
post, snapshot them over time in SQLite, and report per-post / per-account
performance. Snapshots are append-only - keeping history rather than a single
current number is what lets us measure view velocity (views in the first 24/48h),
which is the metric that actually predicts platform pushes and, later, feeds
detector-weight tuning per audience.
"""
from __future__ import annotations

import csv
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from .publish.scheduler import Queue

_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    platform    TEXT NOT NULL,
    external_id TEXT NOT NULL,
    fetched_at  TEXT NOT NULL,
    views       INTEGER NOT NULL DEFAULT 0,
    likes       INTEGER NOT NULL DEFAULT 0,
    comments    INTEGER NOT NULL DEFAULT 0,
    shares      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_snapshots_video ON snapshots (platform, external_id, fetched_at);
"""


@dataclass
class Snapshot:
    platform: str
    external_id: str
    fetched_at: str
    views: int
    likes: int
    comments: int
    shares: int


@dataclass
class ReportRow:
    post_id: int
    platform: str
    account: str
    title: str
    external_id: str
    published_at: str
    views: int
    likes: int
    comments: int
    shares: int


class StatsStore:
    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> StatsStore:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def record(
        self,
        platform: str,
        external_id: str,
        metrics: dict,
        fetched_at: datetime | None = None,
    ) -> None:
        fetched_at = fetched_at or datetime.now(timezone.utc)
        self._conn.execute(
            """INSERT INTO snapshots
               (platform, external_id, fetched_at, views, likes, comments, shares)
               VALUES (?,?,?,?,?,?,?)""",
            (
                platform, external_id, fetched_at.isoformat(),
                int(metrics.get("views", 0)), int(metrics.get("likes", 0)),
                int(metrics.get("comments", 0)), int(metrics.get("shares", 0)),
            ),
        )
        self._conn.commit()

    def latest(self, platform: str, external_id: str) -> Snapshot | None:
        row = self._conn.execute(
            """SELECT platform, external_id, fetched_at, views, likes, comments, shares
               FROM snapshots WHERE platform=? AND external_id=?
               ORDER BY fetched_at DESC LIMIT 1""",
            (platform, external_id),
        ).fetchone()
        return Snapshot(**dict(row)) if row else None

    def history(self, platform: str, external_id: str) -> list[Snapshot]:
        rows = self._conn.execute(
            """SELECT platform, external_id, fetched_at, views, likes, comments, shares
               FROM snapshots WHERE platform=? AND external_id=?
               ORDER BY fetched_at""",
            (platform, external_id),
        ).fetchall()
        return [Snapshot(**dict(r)) for r in rows]


def sync(
    queue: Queue,
    store: StatsStore,
    fetchers: dict,
    now: datetime | None = None,
) -> int:
    """Fetch and snapshot stats for every published post.

    ``fetchers``: {platform: callable(list[external_id]) -> {id: metrics dict}}.
    Returns the number of snapshots recorded. Platforms without a fetcher are
    skipped (e.g. TikTok before its credentials exist).
    """
    published = [p for p in queue.list(status="published") if p.external_id]
    count = 0
    for platform, fetch in fetchers.items():
        ids = [p.external_id for p in published if p.platform == platform]
        if not ids:
            continue
        for external_id, metrics in fetch(ids).items():
            store.record(platform, external_id, metrics, fetched_at=now)
            count += 1
    return count


def report(queue: Queue, store: StatsStore) -> list[ReportRow]:
    """Latest metrics for every published post, ordered by views descending."""
    rows = []
    for p in queue.list(status="published"):
        if not p.external_id:
            continue
        snap = store.latest(p.platform, p.external_id)
        rows.append(
            ReportRow(
                post_id=p.id,
                platform=p.platform,
                account=p.account,
                title=p.title,
                external_id=p.external_id,
                published_at=p.published_at or "",
                views=snap.views if snap else 0,
                likes=snap.likes if snap else 0,
                comments=snap.comments if snap else 0,
                shares=snap.shares if snap else 0,
            )
        )
    rows.sort(key=lambda r: r.views, reverse=True)
    return rows


def account_totals(rows: list[ReportRow]) -> dict[tuple[str, str], dict]:
    """Aggregate report rows -> {(platform, account): {posts, views, likes}}."""
    totals: dict[tuple[str, str], dict] = {}
    for r in rows:
        key = (r.platform, r.account)
        t = totals.setdefault(key, {"posts": 0, "views": 0, "likes": 0})
        t["posts"] += 1
        t["views"] += r.views
        t["likes"] += r.likes
    return totals


def write_csv(rows: list[ReportRow], path: str) -> str:
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["post_id", "platform", "account", "title", "external_id",
             "published_at", "views", "likes", "comments", "shares"]
        )
        for r in rows:
            writer.writerow(
                [r.post_id, r.platform, r.account, r.title, r.external_id,
                 r.published_at, r.views, r.likes, r.comments, r.shares]
            )
    return path
