"""Shared SQLite store plumbing.

Every store in the package (roster, review, analytics, queue, campaigns,
submissions) opens a connection the same way; this base holds the one copy.
The pre-existing stores keep their local copies for now - new stores should
subclass this.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class SqliteStore:
    SCHEMA = ""  # subclasses provide CREATE TABLE IF NOT EXISTS ... statements

    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self.path = db_path  # so callers can reopen on another thread
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        if self.SCHEMA:
            self._conn.executescript(self.SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self.close()
