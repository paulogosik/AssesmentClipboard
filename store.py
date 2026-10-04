import json
import sqlite3
from datetime import datetime, timezone

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS proposals (
    key TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    account_id TEXT,
    location_slug TEXT,
    payload TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    decided_at TEXT,
    result TEXT
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    locations INTEGER,
    proposals INTEGER,
    new_proposals INTEGER,
    confirmed INTEGER
);
"""

STATUSES = ["pending", "applied", "rejected", "failed", "superseded"]


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path=config.DB_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def save_proposals(conn, proposals):
    created_at = now()
    new = 0
    for p in proposals:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO proposals (key, type, title, account_id, location_slug, payload, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (p["key"], p["type"], p["title"], p["account_id"], p["location_slug"], json.dumps(p), created_at),
        )
        new += cursor.rowcount
    keys = [p["key"] for p in proposals]
    placeholders = ",".join("?" * len(keys)) or "''"
    conn.execute(
        f"UPDATE proposals SET status = 'superseded', decided_at = ? WHERE status = 'pending' AND key NOT IN ({placeholders})",
        [created_at, *keys],
    )
    conn.commit()
    return new


def record_run(conn, locations, proposals, new_proposals, confirmed):
    conn.execute(
        "INSERT INTO runs (started_at, locations, proposals, new_proposals, confirmed) VALUES (?, ?, ?, ?, ?)",
        (now(), locations, proposals, new_proposals, confirmed),
    )
    conn.commit()


def list_proposals(conn, status):
    rows = conn.execute("SELECT * FROM proposals WHERE status = ? ORDER BY type, title", (status,)).fetchall()
    return [hydrate(row) for row in rows]


def get_proposal(conn, key):
    row = conn.execute("SELECT * FROM proposals WHERE key = ?", (key,)).fetchone()
    return hydrate(row) if row else None


def hydrate(row):
    proposal = json.loads(row["payload"])
    proposal.update(status=row["status"], created_at=row["created_at"], decided_at=row["decided_at"])
    proposal["result"] = json.loads(row["result"]) if row["result"] else None
    return proposal


def set_status(conn, key, status, result=None):
    conn.execute(
        "UPDATE proposals SET status = ?, decided_at = ?, result = ? WHERE key = ?",
        (status, now(), json.dumps(result) if result is not None else None, key),
    )
    conn.commit()


def counts(conn):
    rows = conn.execute("SELECT status, COUNT(*) AS n FROM proposals GROUP BY status").fetchall()
    found = {row["status"]: row["n"] for row in rows}
    return {status: found.get(status, 0) for status in STATUSES}


def last_run(conn):
    row = conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    return dict(row) if row else None
