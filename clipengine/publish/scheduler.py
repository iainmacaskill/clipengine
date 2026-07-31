"""Publishing queue + scheduling engine.

Turns rendered clips into a managed posting stream per account:
- posts land only inside configured posting windows (audience-active hours)
- minimum spacing between posts on the same account
- per-account daily cap (platforms throttle/flag bulk posting)
- failed publishes retry on later runs, up to a retry limit

The slot allocator is a pure function over an injected clock so every rule is
unit-testable; the queue is SQLite. ``run_due`` performs the actual publishes
via the platform clients, with the music-DMCA screen applied per item first.
"""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, time as dtime, timedelta, timezone
from zoneinfo import ZoneInfo

_STEP = timedelta(minutes=15)   # slot granularity
_HORIZON_DAYS = 14              # give up if no slot within this many days
_MAX_ATTEMPTS = 3

_SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    platform     TEXT NOT NULL CHECK (platform IN ('youtube', 'tiktok')),
    account      TEXT NOT NULL,
    video_path   TEXT NOT NULL,
    title        TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    tags         TEXT NOT NULL DEFAULT '',
    privacy      TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL CHECK (status IN
                   ('scheduled', 'published', 'failed', 'cancelled')),
    scheduled_at TEXT NOT NULL,
    published_at TEXT,
    external_id  TEXT,
    attempts     INTEGER NOT NULL DEFAULT 0,
    last_error   TEXT,
    created_at   TEXT NOT NULL
);
"""


@dataclass
class ScheduleRules:
    windows: list[str] = field(default_factory=lambda: ["11:00-14:00", "17:00-22:00"])
    min_spacing_hours: float = 3.0
    daily_cap: int = 4
    tz: str = "UTC"


@dataclass
class Post:
    id: int
    platform: str
    account: str
    video_path: str
    title: str
    description: str
    tags: str
    privacy: str
    status: str
    scheduled_at: str
    published_at: str | None
    external_id: str | None
    attempts: int
    last_error: str | None
    created_at: str


def _parse_windows(windows: list[str]) -> list[tuple[dtime, dtime]]:
    out = []
    for w in windows:
        a, b = w.split("-")
        h1, m1 = (int(v) for v in a.split(":"))
        h2, m2 = (int(v) for v in b.split(":"))
        start, end = dtime(h1, m1), dtime(h2, m2)
        if end <= start:
            raise ValueError(f"window end must be after start: {w!r}")
        out.append((start, end))
    return out


def next_slot(
    now: datetime,
    existing: list[datetime],
    rules: ScheduleRules,
) -> datetime:
    """Earliest posting slot >= now satisfying windows, spacing, and daily cap.

    ``existing`` = scheduled/published datetimes for the same account (any order,
    tz-aware). Returned datetime is tz-aware UTC.
    """
    tz = ZoneInfo(rules.tz)
    windows = _parse_windows(rules.windows)
    spacing = timedelta(hours=rules.min_spacing_hours)
    existing = sorted(e.astimezone(timezone.utc) for e in existing)
    now = now.astimezone(timezone.utc)

    # round now up to the next step boundary
    t = now + (datetime.min.replace(tzinfo=timezone.utc) - now) % _STEP
    end = now + timedelta(days=_HORIZON_DAYS)
    while t <= end:
        local = t.astimezone(tz)
        in_window = any(a <= local.time() < b for a, b in windows)
        if in_window:
            same_day = [e for e in existing if e.astimezone(tz).date() == local.date()]
            spaced = all(abs(t - e) >= spacing for e in existing)
            if len(same_day) < rules.daily_cap and spaced:
                return t
        t += _STEP
    raise RuntimeError(
        f"no free slot within {_HORIZON_DAYS} days - queue is saturated for this account"
    )


class Queue:
    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Queue:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- scheduling -------------------------------------------------------

    def _active_times(self, platform: str, account: str) -> list[datetime]:
        rows = self._conn.execute(
            """SELECT scheduled_at FROM posts
               WHERE platform=? AND account=? AND status IN ('scheduled', 'published')""",
            (platform, account),
        ).fetchall()
        return [datetime.fromisoformat(r["scheduled_at"]) for r in rows]

    def add(
        self,
        platform: str,
        account: str,
        video_path: str,
        title: str,
        rules: ScheduleRules,
        description: str = "",
        tags: str = "",
        privacy: str = "",
        now: datetime | None = None,
    ) -> Post:
        now = now or datetime.now(timezone.utc)
        slot = next_slot(now, self._active_times(platform, account), rules)
        cur = self._conn.execute(
            """INSERT INTO posts (platform, account, video_path, title, description,
                 tags, privacy, status, scheduled_at, created_at)
               VALUES (?,?,?,?,?,?,?,'scheduled',?,?)""",
            (
                platform, account, video_path, title, description, tags, privacy,
                slot.isoformat(), now.isoformat(),
            ),
        )
        self._conn.commit()
        post = self.get(cur.lastrowid)
        assert post is not None
        return post

    def get(self, post_id: int) -> Post | None:
        row = self._conn.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
        return Post(**dict(row)) if row else None

    def list(self, status: str | None = None) -> list[Post]:
        q, params = "SELECT * FROM posts", ()
        if status:
            q, params = q + " WHERE status=?", (status,)
        rows = self._conn.execute(q + " ORDER BY scheduled_at", params).fetchall()
        return [Post(**dict(r)) for r in rows]

    def cancel(self, post_id: int) -> Post:
        post = self.get(post_id)
        if post is None:
            raise LookupError(f"no post {post_id}")
        if post.status != "scheduled":
            raise ValueError(f"post {post_id} is {post.status}, not scheduled")
        self._conn.execute("UPDATE posts SET status='cancelled' WHERE id=?", (post_id,))
        self._conn.commit()
        return self.get(post_id)  # type: ignore[return-value]

    # -- execution --------------------------------------------------------

    def due(self, now: datetime | None = None) -> list[Post]:
        now = now or datetime.now(timezone.utc)
        return [
            p
            for p in self.list(status="scheduled")
            if datetime.fromisoformat(p.scheduled_at) <= now
        ]

    def mark_published(self, post_id: int, external_id: str, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        self._conn.execute(
            """UPDATE posts SET status='published', published_at=?, external_id=?
               WHERE id=?""",
            (now.isoformat(), external_id, post_id),
        )
        self._conn.commit()

    def mark_attempt_failed(self, post_id: int, error: str) -> None:
        """Record a failed attempt; the post retries on later runs until the limit."""
        post = self.get(post_id)
        assert post is not None
        attempts = post.attempts + 1
        status = "failed" if attempts >= _MAX_ATTEMPTS else "scheduled"
        self._conn.execute(
            "UPDATE posts SET attempts=?, last_error=?, status=? WHERE id=?",
            (attempts, error[:500], status, post_id),
        )
        self._conn.commit()


def run_due(
    queue: Queue,
    publishers: dict,
    screen,
    now: datetime | None = None,
) -> list[tuple[Post, str | None]]:
    """Publish every due post. Returns [(post, external_id-or-None)].

    ``publishers``: {platform: callable(Post) -> external_id}.
    ``screen``: callable(video_path) -> bool (True = clean); flagged posts fail
    the attempt so they can be muted and retried.
    """
    results: list[tuple[Post, str | None]] = []
    for post in queue.due(now):
        try:
            if not screen(post.video_path):
                raise RuntimeError(
                    "music-DMCA screen flagged this clip - mute it "
                    "(clipengine music-check --mute) and re-queue"
                )
            external_id = publishers[post.platform](post)
            queue.mark_published(post.id, external_id, now)
            results.append((queue.get(post.id), external_id))  # type: ignore[arg-type]
        except Exception as e:  # noqa: BLE001 - record any failure and continue
            queue.mark_attempt_failed(post.id, str(e))
            results.append((queue.get(post.id), None))  # type: ignore[arg-type]
    return results
