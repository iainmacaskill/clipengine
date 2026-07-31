"""Streamer permission roster.

The rights layer's ground truth (product plan §2): a streamer may only be
ingested while the roster holds a current permission record for them. Every
record must cite its evidence - a published clip-policy URL or a stored opt-in
consent reference. Ingestion commands call require() and refuse to run without
an allowed record; revocation takes effect immediately at the gate (published
-clip takedown within 24h is handled by ops, outside this module).
"""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

VALID_SOURCES = ("published_policy", "opt_in", "licence")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS streamers (
    login       TEXT PRIMARY KEY,
    status      TEXT NOT NULL CHECK (status IN ('allowed', 'revoked')),
    source      TEXT NOT NULL CHECK (source IN ('published_policy', 'opt_in', 'licence')),
    evidence    TEXT NOT NULL,
    credit      TEXT NOT NULL DEFAULT '',
    exclusions  TEXT NOT NULL DEFAULT '',
    notes       TEXT NOT NULL DEFAULT '',
    granted_at  TEXT NOT NULL,
    revoked_at  TEXT
);
"""


class PermissionError_(PermissionError):
    """Raised when ingestion is attempted for a streamer without permission."""


@dataclass
class RosterEntry:
    login: str
    status: str
    source: str
    evidence: str
    credit: str
    exclusions: str
    notes: str
    granted_at: str
    revoked_at: str | None

    @property
    def allowed(self) -> bool:
        return self.status == "allowed"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Roster:
    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Roster:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def add(
        self,
        login: str,
        source: str,
        evidence: str,
        credit: str = "",
        exclusions: str = "",
        notes: str = "",
    ) -> RosterEntry:
        """Record (or re-grant) permission. Evidence is mandatory - no record, no grant."""
        login = login.strip().lower()
        if not login:
            raise ValueError("streamer login required")
        if source not in VALID_SOURCES:
            raise ValueError(f"source must be one of {VALID_SOURCES}")
        if not evidence.strip():
            raise ValueError(
                "evidence required: a clip-policy URL or stored consent reference"
            )
        self._conn.execute(
            """INSERT INTO streamers
               (login, status, source, evidence, credit, exclusions, notes, granted_at, revoked_at)
               VALUES (?, 'allowed', ?, ?, ?, ?, ?, ?, NULL)
               ON CONFLICT(login) DO UPDATE SET
                 status='allowed', source=excluded.source, evidence=excluded.evidence,
                 credit=excluded.credit, exclusions=excluded.exclusions,
                 notes=excluded.notes, granted_at=excluded.granted_at, revoked_at=NULL""",
            (login, source, evidence.strip(), credit, exclusions, notes, _now()),
        )
        self._conn.commit()
        entry = self.get(login)
        assert entry is not None
        return entry

    def revoke(self, login: str, reason: str = "") -> RosterEntry:
        """Revoke permission, effective immediately at the ingestion gate."""
        login = login.strip().lower()
        entry = self.get(login)
        if entry is None:
            raise LookupError(f"{login} is not on the roster")
        notes = (entry.notes + "\n" if entry.notes else "") + f"revoked: {reason}".strip()
        self._conn.execute(
            "UPDATE streamers SET status='revoked', revoked_at=?, notes=? WHERE login=?",
            (_now(), notes, login),
        )
        self._conn.commit()
        entry = self.get(login)
        assert entry is not None
        return entry

    def get(self, login: str) -> RosterEntry | None:
        row = self._conn.execute(
            "SELECT * FROM streamers WHERE login=?", (login.strip().lower(),)
        ).fetchone()
        return RosterEntry(**dict(row)) if row else None

    def list(self, status: str | None = None) -> list[RosterEntry]:
        query = "SELECT * FROM streamers"
        params: tuple = ()
        if status:
            query += " WHERE status=?"
            params = (status,)
        rows = self._conn.execute(query + " ORDER BY login", params).fetchall()
        return [RosterEntry(**dict(r)) for r in rows]

    def import_csv(
        self, path: str, default_source: str = "published_policy"
    ) -> tuple[list[RosterEntry], list[str]]:
        """Bulk-add streamers from CSV -> (imported entries, per-row errors).

        Columns: ``login`` and ``evidence`` required; ``source`` (defaults to
        ``default_source``), ``credit``, ``exclusions``, ``notes`` optional; extra
        columns ignored. A bad row is reported and skipped, the rest import.
        """
        import csv as _csv

        imported: list[RosterEntry] = []
        errors: list[str] = []
        with open(path, newline="") as f:
            reader = _csv.DictReader(f)
            if reader.fieldnames is None or "login" not in reader.fieldnames:
                raise ValueError("CSV needs a header row with at least: login,evidence")
            for lineno, row in enumerate(reader, start=2):
                try:
                    imported.append(
                        self.add(
                            row.get("login", ""),
                            source=(row.get("source") or default_source).strip(),
                            evidence=row.get("evidence", ""),
                            credit=(row.get("credit") or "").strip(),
                            exclusions=(row.get("exclusions") or "").strip(),
                            notes=(row.get("notes") or "").strip(),
                        )
                    )
                except (ValueError, KeyError) as e:
                    errors.append(f"row {lineno} ({row.get('login', '?')}): {e}")
        return imported, errors

    def export_csv(self, path: str) -> int:
        """Write the whole roster (all statuses) to CSV; returns the row count."""
        import csv as _csv

        entries = self.list()
        with open(path, "w", newline="") as f:
            writer = _csv.writer(f)
            writer.writerow(
                ["login", "status", "source", "evidence", "credit",
                 "exclusions", "notes", "granted_at", "revoked_at"]
            )
            for e in entries:
                writer.writerow(
                    [e.login, e.status, e.source, e.evidence, e.credit,
                     e.exclusions, e.notes, e.granted_at, e.revoked_at or ""]
                )
        return len(entries)

    def require(self, login: str) -> RosterEntry:
        """Gate call for ingestion: return the allowed entry or raise."""
        entry = self.get(login)
        if entry is None:
            raise PermissionError_(
                f"'{login}' is not on the permission roster - ingestion refused. "
                f"Record their permission first: clipengine roster add {login} "
                f"--source published_policy|opt_in|licence --evidence <url-or-ref>"
            )
        if not entry.allowed:
            raise PermissionError_(
                f"permission for '{login}' was revoked ({entry.revoked_at}) - "
                f"ingestion refused"
            )
        return entry
