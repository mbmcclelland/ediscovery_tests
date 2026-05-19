"""
SQLite TSDB for the recorder.

Schema is intentionally small. Three tables:
  - metrics: long/narrow time series (ts, signal, value)
  - events:  campaign-relevant moments (start, adjust, annotate, yellow, red, end)
  - campaigns: header rows for each campaign

Retention policy lives in `recorder.retention` (not in this file).
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

SCHEMA_VERSION = 1

_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=OFF;

CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS metrics (
    ts     INTEGER NOT NULL,
    signal TEXT    NOT NULL,
    value  REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_metrics_signal_ts ON metrics(signal, ts);
CREATE INDEX IF NOT EXISTS idx_metrics_ts ON metrics(ts);

CREATE TABLE IF NOT EXISTS events (
    ts       INTEGER NOT NULL,
    kind     TEXT    NOT NULL,
    campaign TEXT,
    payload  TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_events_campaign ON events(campaign);

CREATE TABLE IF NOT EXISTS campaigns (
    name           TEXT PRIMARY KEY,
    started_at     INTEGER NOT NULL,
    ended_at       INTEGER,
    scenario       TEXT,
    initial_users  INTEGER,
    current_users  INTEGER,
    notes          TEXT
);
"""


def default_db_path() -> Path:
    """Where the recorder writes by default.

    Falls back to a user-writable location if /var/lib isn't writable
    (so non-root tests can use the same code path).
    """
    candidates = [
        Path("/var/lib/dr-load-recorder/store.db"),
        Path.home() / ".local/share/dr-load-recorder/store.db",
        Path("/tmp/dr-load-recorder/store.db"),
    ]
    for p in candidates:
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            # Quick write check
            tmp = p.parent / ".write_test"
            tmp.touch()
            tmp.unlink()
            return p
        except (OSError, PermissionError):
            continue
    raise RuntimeError("No writable location for the recorder store")


class Store:
    """Thin wrapper over a SQLite TSDB.

    Same instance can be used for reads and writes. Connection is opened
    lazily and reused across calls (sqlite3 is thread-local; this class
    is NOT thread-safe — open one per thread if you need parallelism).
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_schema()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.path, isolation_level=None)  # autocommit
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_schema(self) -> None:
        with self._cursor() as c:
            c.executescript(_SCHEMA)
            row = c.execute(
                "SELECT value FROM schema_meta WHERE key = 'version'"
            ).fetchone()
            if row is None:
                c.execute(
                    "INSERT INTO schema_meta(key, value) VALUES ('version', ?)",
                    (str(SCHEMA_VERSION),),
                )

    @contextmanager
    def _cursor(self) -> Iterator[sqlite3.Cursor]:
        c = self.conn.cursor()
        try:
            yield c
        finally:
            c.close()

    # --- metrics ---

    def write_metrics(self, ts: int, samples: dict[str, float]) -> None:
        """Insert one row per (signal, value) at timestamp `ts`."""
        rows = [(ts, k, float(v)) for k, v in samples.items() if v is not None]
        if not rows:
            return
        with self._cursor() as c:
            c.executemany(
                "INSERT INTO metrics(ts, signal, value) VALUES (?, ?, ?)", rows
            )

    def read_metric(
        self,
        signal: str,
        since: Optional[int] = None,
        until: Optional[int] = None,
    ) -> list[tuple[int, float]]:
        q = "SELECT ts, value FROM metrics WHERE signal = ?"
        args: list[Any] = [signal]
        if since is not None:
            q += " AND ts >= ?"
            args.append(since)
        if until is not None:
            q += " AND ts <= ?"
            args.append(until)
        q += " ORDER BY ts"
        with self._cursor() as c:
            return [(r["ts"], r["value"]) for r in c.execute(q, args)]

    def latest_metric(self, signal: str) -> Optional[tuple[int, float]]:
        with self._cursor() as c:
            row = c.execute(
                "SELECT ts, value FROM metrics WHERE signal = ? ORDER BY ts DESC LIMIT 1",
                (signal,),
            ).fetchone()
            return (row["ts"], row["value"]) if row else None

    def signals(self) -> list[str]:
        with self._cursor() as c:
            return [r[0] for r in c.execute("SELECT DISTINCT signal FROM metrics")]

    # --- events ---

    def write_event(
        self,
        kind: str,
        *,
        campaign: Optional[str] = None,
        payload: Optional[dict] = None,
        ts: Optional[int] = None,
    ) -> None:
        with self._cursor() as c:
            c.execute(
                "INSERT INTO events(ts, kind, campaign, payload) VALUES (?, ?, ?, ?)",
                (
                    ts or int(time.time()),
                    kind,
                    campaign,
                    json.dumps(payload) if payload else None,
                ),
            )

    def read_events(
        self,
        since: Optional[int] = None,
        until: Optional[int] = None,
        kind: Optional[str] = None,
        campaign: Optional[str] = None,
    ) -> list[dict]:
        q = "SELECT ts, kind, campaign, payload FROM events WHERE 1=1"
        args: list[Any] = []
        if since is not None:
            q += " AND ts >= ?"
            args.append(since)
        if until is not None:
            q += " AND ts <= ?"
            args.append(until)
        if kind is not None:
            q += " AND kind = ?"
            args.append(kind)
        if campaign is not None:
            q += " AND campaign = ?"
            args.append(campaign)
        q += " ORDER BY ts"
        with self._cursor() as c:
            out: list[dict] = []
            for r in c.execute(q, args):
                d = dict(r)
                if d.get("payload"):
                    try:
                        d["payload"] = json.loads(d["payload"])
                    except (TypeError, ValueError):
                        pass
                out.append(d)
            return out

    # --- campaigns ---

    def start_campaign(
        self,
        name: str,
        scenario: Optional[str] = None,
        initial_users: Optional[int] = None,
        notes: Optional[str] = None,
        ts: Optional[int] = None,
    ) -> None:
        started = ts or int(time.time())
        with self._cursor() as c:
            c.execute(
                """INSERT OR REPLACE INTO campaigns
                   (name, started_at, ended_at, scenario, initial_users, current_users, notes)
                   VALUES (?, ?, NULL, ?, ?, ?, ?)""",
                (name, started, scenario, initial_users, initial_users, notes),
            )
        self.write_event(
            "START",
            campaign=name,
            payload={"scenario": scenario, "users": initial_users},
            ts=started,
        )

    def adjust_campaign(self, name: str, users: int, note: Optional[str] = None) -> None:
        with self._cursor() as c:
            c.execute(
                "UPDATE campaigns SET current_users = ? WHERE name = ?", (users, name)
            )
        self.write_event(
            "ADJUST",
            campaign=name,
            payload={"users": users, "note": note},
        )

    def end_campaign(self, name: str, note: Optional[str] = None) -> None:
        ended = int(time.time())
        with self._cursor() as c:
            c.execute(
                "UPDATE campaigns SET ended_at = ? WHERE name = ?", (ended, name)
            )
        self.write_event(
            "END",
            campaign=name,
            payload={"note": note} if note else None,
            ts=ended,
        )

    def active_campaign(self) -> Optional[dict]:
        with self._cursor() as c:
            row = c.execute(
                "SELECT * FROM campaigns WHERE ended_at IS NULL ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
            return dict(row) if row else None

    def campaign(self, name: str) -> Optional[dict]:
        with self._cursor() as c:
            row = c.execute(
                "SELECT * FROM campaigns WHERE name = ?", (name,)
            ).fetchone()
            return dict(row) if row else None

    def all_campaigns(self) -> list[dict]:
        with self._cursor() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM campaigns ORDER BY started_at DESC"
            )]

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
