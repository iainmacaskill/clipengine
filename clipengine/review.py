"""Human review queue for rendered clips.

The MVP quality bar (plan §6) is measured here: candidate clips enter as
*pending* from a batch manifest, a human approves (with a real title) or
rejects (with a reason), and the pass rate is the plan's >=50% criterion.
Approvals flow into the publish scheduling queue; rejection reasons accumulate
as labelled data for detector tuning.
"""
from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

_SCHEMA = """
CREATE TABLE IF NOT EXISTS clips (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    clip_path  TEXT NOT NULL UNIQUE,
    streamer   TEXT NOT NULL,
    start      REAL NOT NULL,
    end        REAL NOT NULL,
    score      REAL NOT NULL DEFAULT 0,
    signals    TEXT NOT NULL DEFAULT '{}',
    muted      TEXT NOT NULL DEFAULT '[]',
    status     TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected')),
    title      TEXT,
    reason     TEXT,
    decided_at TEXT,
    queued_post_id INTEGER,
    created_at TEXT NOT NULL
);
"""


@dataclass
class ReviewClip:
    id: int
    clip_path: str
    streamer: str
    start: float
    end: float
    score: float
    signals: str
    muted: str
    status: str
    title: str | None
    reason: str | None
    decided_at: str | None
    queued_post_id: int | None
    created_at: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ReviewQueue:
    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> ReviewQueue:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- intake -----------------------------------------------------------

    def import_manifest(self, manifest_path: str) -> tuple[int, int]:
        """Add a batch manifest's rendered clips as pending -> (added, skipped).

        Clips already imported (same path) and failed renders are skipped.
        """
        with open(manifest_path) as f:
            manifest = json.load(f)
        added = skipped = 0
        for item in manifest:
            if item.get("status") != "rendered":
                skipped += 1
                continue
            try:
                self._conn.execute(
                    """INSERT INTO clips (clip_path, streamer, start, end, score,
                         signals, muted, status, created_at)
                       VALUES (?,?,?,?,?,?,?,'pending',?)""",
                    (
                        item["path"], item.get("streamer", ""), item["start"], item["end"],
                        item.get("score", 0.0), json.dumps(item.get("signals", {})),
                        json.dumps(item.get("muted_segments", [])), _now(),
                    ),
                )
                added += 1
            except sqlite3.IntegrityError:
                skipped += 1
        self._conn.commit()
        return added, skipped

    # -- decisions --------------------------------------------------------

    def get(self, clip_id: int) -> ReviewClip | None:
        row = self._conn.execute("SELECT * FROM clips WHERE id=?", (clip_id,)).fetchone()
        return ReviewClip(**dict(row)) if row else None

    def list(self, status: str | None = None) -> list[ReviewClip]:
        q, params = "SELECT * FROM clips", ()
        if status:
            q, params = q + " WHERE status=?", (status,)
        rows = self._conn.execute(q + " ORDER BY id", params).fetchall()
        return [ReviewClip(**dict(r)) for r in rows]

    def _require_pending(self, clip_id: int) -> ReviewClip:
        clip = self.get(clip_id)
        if clip is None:
            raise LookupError(f"no clip {clip_id}")
        if clip.status != "pending":
            raise ValueError(f"clip {clip_id} already {clip.status}")
        return clip

    def approve(self, clip_id: int, title: str, queued_post_id: int | None = None) -> ReviewClip:
        if not title.strip():
            raise ValueError("an approved clip needs a real title")
        self._require_pending(clip_id)
        self._conn.execute(
            """UPDATE clips SET status='approved', title=?, decided_at=?,
               queued_post_id=? WHERE id=?""",
            (title.strip(), _now(), queued_post_id, clip_id),
        )
        self._conn.commit()
        return self.get(clip_id)  # type: ignore[return-value]

    def reject(self, clip_id: int, reason: str) -> ReviewClip:
        if not reason.strip():
            raise ValueError(
                "a rejection needs a reason - reasons are the tuning signal "
                "(e.g. 'not funny', 'cut too early', 'bad facecam crop')"
            )
        self._require_pending(clip_id)
        self._conn.execute(
            "UPDATE clips SET status='rejected', reason=?, decided_at=? WHERE id=?",
            (reason.strip(), _now(), clip_id),
        )
        self._conn.commit()
        return self.get(clip_id)  # type: ignore[return-value]

    # -- metrics ----------------------------------------------------------

    def stats(self) -> dict:
        """Pass-rate metrics. MVP criterion (plan §6): pass_rate >= 0.5."""
        rows = self.list()
        approved = [c for c in rows if c.status == "approved"]
        rejected = [c for c in rows if c.status == "rejected"]
        decided = len(approved) + len(rejected)
        reasons: dict[str, int] = {}
        for c in rejected:
            key = (c.reason or "").strip().lower()
            reasons[key] = reasons.get(key, 0) + 1
        return {
            "pending": sum(1 for c in rows if c.status == "pending"),
            "approved": len(approved),
            "rejected": len(rejected),
            "pass_rate": len(approved) / decided if decided else None,
            "rejection_reasons": dict(
                sorted(reasons.items(), key=lambda kv: -kv[1])
            ),
        }
