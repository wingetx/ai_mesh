"""
bus.py — SQLite-backed pub/sub message bus.

Every message is a row. Every row is durable. Anyone with the DB file can
read the entire history. There are no in-memory channels, no daemons, no
sockets. Two processes coordinate purely by reading and writing the same
SQLite file.

Schema:
    messages(id, ts, channel, sender, kind, body, in_reply_to)

`Bus.send()`  → INSERT
`Bus.fetch()` → SELECT rows after a given id on the requested channels
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable, Optional

DEFAULT_DB = Path(
    os.environ.get("AI_MESH_DB")
    or (Path.home() / ".ai-mesh" / "bus.db")
)


@dataclass
class Envelope:
    """A single message on the bus."""

    id: Optional[int]
    ts: float
    channel: str
    sender: str
    kind: str  # free-form: "say", "ask", "answer", "tool_result", ...
    body: Any  # JSON-serializable
    to: Optional[str] = None  # if set, addresses one specific agent
    in_reply_to: Optional[str] = None
    msg_uid: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def as_dict(self) -> dict:
        d = asdict(self)
        return d


class Bus:
    """Local SQLite pub/sub bus."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS messages (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        ts           REAL    NOT NULL,
        channel      TEXT    NOT NULL,
        sender       TEXT    NOT NULL,
        kind         TEXT    NOT NULL,
        body         TEXT    NOT NULL,
        recipient    TEXT,
        in_reply_to  TEXT,
        msg_uid      TEXT    NOT NULL UNIQUE
    );
    CREATE INDEX IF NOT EXISTS idx_messages_channel_id
        ON messages(channel, id);
    CREATE INDEX IF NOT EXISTS idx_messages_ts ON messages(ts);
    """

    def __init__(self, db_path: Path | str = DEFAULT_DB):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ── lifecycle ───────────────────────────────────────────────────────
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.db_path,
            isolation_level=None,  # autocommit; explicit transactions when needed
            timeout=10,
        )
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(self.SCHEMA)
            # Lightweight migration: add `recipient` column to older DBs.
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(messages)")}
            if "recipient" not in cols:
                conn.execute("ALTER TABLE messages ADD COLUMN recipient TEXT")

    # ── producer ────────────────────────────────────────────────────────
    def send(
        self,
        channel: str,
        sender: str,
        body: Any,
        kind: str = "say",
        to: Optional[str] = None,
        in_reply_to: Optional[str] = None,
    ) -> Envelope:
        """Publish a message. Returns the envelope with id and msg_uid filled."""
        env = Envelope(
            id=None,
            ts=time.time(),
            channel=channel,
            sender=sender,
            kind=kind,
            body=body,
            to=to,
            in_reply_to=in_reply_to,
        )
        payload = json.dumps(env.body, ensure_ascii=False, default=str)
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO messages "
                "(ts, channel, sender, kind, body, recipient, in_reply_to, msg_uid) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    env.ts,
                    env.channel,
                    env.sender,
                    env.kind,
                    payload,
                    env.to,
                    env.in_reply_to,
                    env.msg_uid,
                ),
            )
            env.id = int(cur.lastrowid)
        return env

    # ── consumer ────────────────────────────────────────────────────────
    def fetch(
        self,
        channels: Iterable[str],
        after_id: int = 0,
        limit: int = 100,
    ) -> list[Envelope]:
        """Return messages on the given channels with id > after_id."""
        chans = list(channels)
        if not chans:
            return []
        placeholders = ",".join("?" * len(chans))
        sql = (
            f"SELECT * FROM messages "
            f"WHERE channel IN ({placeholders}) AND id > ? "
            f"ORDER BY id ASC LIMIT ?"
        )
        with self._connect() as conn:
            rows = conn.execute(sql, (*chans, after_id, limit)).fetchall()
        return [self._row_to_envelope(r) for r in rows]

    def tail(self, n: int = 20, channel: Optional[str] = None) -> list[Envelope]:
        """Return the last n messages, optionally filtered by channel."""
        with self._connect() as conn:
            if channel:
                rows = conn.execute(
                    "SELECT * FROM (SELECT * FROM messages WHERE channel = ? "
                    "ORDER BY id DESC LIMIT ?) ORDER BY id ASC",
                    (channel, n),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM (SELECT * FROM messages "
                    "ORDER BY id DESC LIMIT ?) ORDER BY id ASC",
                    (n,),
                ).fetchall()
        return [self._row_to_envelope(r) for r in rows]

    def channels(self) -> list[tuple[str, int]]:
        """List channels with traffic counts."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT channel, COUNT(*) AS n FROM messages "
                "GROUP BY channel ORDER BY n DESC"
            ).fetchall()
        return [(r["channel"], int(r["n"])) for r in rows]

    # ── helpers ─────────────────────────────────────────────────────────
    @staticmethod
    def _row_to_envelope(row: sqlite3.Row) -> Envelope:
        try:
            body = json.loads(row["body"])
        except (TypeError, ValueError):
            body = row["body"]
        # Older rows may not have the recipient column populated.
        try:
            recipient = row["recipient"]
        except (IndexError, KeyError):
            recipient = None
        return Envelope(
            id=int(row["id"]),
            ts=float(row["ts"]),
            channel=row["channel"],
            sender=row["sender"],
            kind=row["kind"],
            body=body,
            to=recipient,
            in_reply_to=row["in_reply_to"],
            msg_uid=row["msg_uid"],
        )
