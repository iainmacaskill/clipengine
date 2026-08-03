"""Source tracker for the web UI: the approved videos a campaign is clipped from.

The engine has no source-material store (the CLI takes file paths), so the UI
needs one to remember what's been added, downloaded, and transcribed. It lives
in its OWN database (sources.db) beside campaigns.db - never a new table in the
campaign store - so the live campaigns DB schema is untouched.
"""
from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass

from ..db import SqliteStore, utc_now

# pending -> downloading -> transcribing -> ready ; error at any point
STATUSES = ("pending", "downloading", "transcribing", "ready", "error")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id  TEXT NOT NULL,
    title        TEXT NOT NULL DEFAULT '',
    url          TEXT NOT NULL DEFAULT '',
    path         TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'pending',
    duration_s   REAL NOT NULL DEFAULT 0,
    detail       TEXT NOT NULL DEFAULT '',
    added_at     TEXT NOT NULL,
    UNIQUE (campaign_id, url, path)
);
"""


@dataclass
class Source:
    id: int
    campaign_id: str
    title: str
    url: str
    path: str
    status: str
    duration_s: float
    detail: str
    added_at: str

    def to_dict(self) -> dict:
        return asdict(self)


class SourceStore(SqliteStore):
    SCHEMA = _SCHEMA

    def add(
        self, campaign_id: str, url: str = "", path: str = "", title: str = ""
    ) -> Source:
        url, path = url.strip(), path.strip()
        if not url and not path:
            raise ValueError("a source needs a link or a file path")
        try:
            cur = self._conn.execute(
                """INSERT INTO sources (campaign_id, title, url, path, status, added_at)
                   VALUES (?,?,?,?,?,?)""",
                (campaign_id, title.strip(), url, path,
                 "ready" if path else "pending", utc_now()),
            )
        except sqlite3.IntegrityError:
            raise ValueError("that source is already added to this campaign") from None
        self._conn.commit()
        return self.get(cur.lastrowid)

    def get(self, source_id: int) -> Source:
        row = self._conn.execute(
            "SELECT * FROM sources WHERE id=?", (source_id,)
        ).fetchone()
        if row is None:
            raise LookupError(f"no source #{source_id}")
        return Source(**dict(row))

    def list(self, campaign_id: str | None = None) -> list[Source]:
        if campaign_id:
            rows = self._conn.execute(
                "SELECT * FROM sources WHERE campaign_id=? ORDER BY id", (campaign_id,)
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM sources ORDER BY id").fetchall()
        return [Source(**dict(r)) for r in rows]

    def update(self, source_id: int, **fields) -> Source:
        allowed = {"title", "url", "path", "status", "duration_s", "detail"}
        sets = {k: v for k, v in fields.items() if k in allowed}
        if sets:
            cols = ", ".join(f"{k}=?" for k in sets)
            self._conn.execute(
                f"UPDATE sources SET {cols} WHERE id=?",
                (*sets.values(), source_id),
            )
            self._conn.commit()
        return self.get(source_id)
