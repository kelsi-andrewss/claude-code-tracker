#!/usr/bin/env python3
"""SQLite storage module for Claude Code Tracker.

Flat-function API for all DB operations. Replaces flat JSON file storage
with a WAL-mode SQLite backend. Handles auto-migration from existing
tokens.json / agents.json on first access.
"""
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from typing import Optional

DB_NAME = "tracking.db"

TURN_COLS = [
    "session_id", "turn_index", "date", "project", "turn_timestamp",
    "input_tokens", "cache_creation_tokens", "cache_read_tokens",
    "output_tokens", "total_tokens", "estimated_cost_usd", "model",
    "duration_seconds",
]

TURN_DEFAULTS = {
    "turn_timestamp": None,
    "input_tokens": 0,
    "cache_creation_tokens": 0,
    "cache_read_tokens": 0,
    "output_tokens": 0,
    "total_tokens": 0,
    "estimated_cost_usd": 0,
    "model": "unknown",
    "duration_seconds": 0,
}

AGENT_COLS = [
    "timestamp", "session_id", "agent_id", "agent_type",
    "input_tokens", "output_tokens", "cache_creation_tokens",
    "cache_read_tokens", "total_tokens", "turns",
    "estimated_cost_usd", "model",
]

AGENT_DEFAULTS = {
    "agent_type": "unknown",
    "input_tokens": 0,
    "output_tokens": 0,
    "cache_creation_tokens": 0,
    "cache_read_tokens": 0,
    "total_tokens": 0,
    "turns": 0,
    "estimated_cost_usd": 0,
    "model": "unknown",
}

SKILL_COLS = [
    "session_id", "date", "project", "skill_name", "args",
    "tool_use_id", "timestamp", "duration_seconds",
    "success", "error_message",
]

SKILL_DEFAULTS = {
    "args": None,
    "tool_use_id": None,
    "timestamp": None,
    "duration_seconds": 0,
    "success": 1,
    "error_message": None,
}

SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS turns (
    session_id TEXT NOT NULL,
    turn_index INTEGER NOT NULL,
    date TEXT NOT NULL,
    project TEXT NOT NULL,
    turn_timestamp TEXT,
    input_tokens INTEGER DEFAULT 0,
    cache_creation_tokens INTEGER DEFAULT 0,
    cache_read_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    estimated_cost_usd REAL DEFAULT 0,
    model TEXT DEFAULT 'unknown',
    duration_seconds INTEGER DEFAULT 0,
    PRIMARY KEY (session_id, turn_index)
);
CREATE INDEX IF NOT EXISTS idx_turns_date ON turns(date);

CREATE TABLE IF NOT EXISTS agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    session_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    agent_type TEXT DEFAULT 'unknown',
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cache_creation_tokens INTEGER DEFAULT 0,
    cache_read_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    turns INTEGER DEFAULT 0,
    estimated_cost_usd REAL DEFAULT 0,
    model TEXT DEFAULT 'unknown'
);
CREATE INDEX IF NOT EXISTS idx_agents_session ON agents(session_id);

CREATE TABLE IF NOT EXISTS skills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    date TEXT NOT NULL,
    project TEXT NOT NULL,
    skill_name TEXT NOT NULL,
    args TEXT,
    tool_use_id TEXT,
    timestamp TEXT,
    duration_seconds INTEGER DEFAULT 0,
    success INTEGER DEFAULT 1,
    error_message TEXT
);
CREATE INDEX IF NOT EXISTS idx_skills_session ON skills(session_id);
CREATE INDEX IF NOT EXISTS idx_skills_name ON skills(skill_name);

CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _db_path(tracking_dir: str) -> str:
    return os.path.join(tracking_dir, DB_NAME)


def _insert_turns(conn: sqlite3.Connection, entries: list[dict]) -> None:
    """INSERT OR REPLACE turns via executemany."""
    placeholders = ", ".join(["?"] * len(TURN_COLS))
    sql = f"INSERT OR REPLACE INTO turns ({', '.join(TURN_COLS)}) VALUES ({placeholders})"
    rows = []
    for e in entries:
        rows.append(tuple(e.get(col, TURN_DEFAULTS.get(col)) for col in TURN_COLS))
    if rows:
        conn.executemany(sql, rows)


def _insert_agents(conn: sqlite3.Connection, entries: list[dict]) -> None:
    """INSERT agents via executemany (always appends — autoincrement id)."""
    placeholders = ", ".join(["?"] * len(AGENT_COLS))
    sql = f"INSERT INTO agents ({', '.join(AGENT_COLS)}) VALUES ({placeholders})"
    rows = []
    for e in entries:
        rows.append(tuple(e.get(col, AGENT_DEFAULTS.get(col)) for col in AGENT_COLS))
    if rows:
        conn.executemany(sql, rows)


def _insert_skills(conn: sqlite3.Connection, entries: list[dict]) -> None:
    """INSERT skills via executemany (always appends — autoincrement id)."""
    placeholders = ", ".join(["?"] * len(SKILL_COLS))
    sql = f"INSERT INTO skills ({', '.join(SKILL_COLS)}) VALUES ({placeholders})"
    rows = []
    for e in entries:
        rows.append(tuple(e.get(col, SKILL_DEFAULTS.get(col)) for col in SKILL_COLS))
    if rows:
        conn.executemany(sql, rows)


def _maybe_migrate(conn: sqlite3.Connection, tracking_dir: str) -> None:
    """One-time migration from JSON files to SQLite.

    Checks metadata for 'migrated_at'. If absent and JSON files exist,
    imports their data, stamps metadata, and renames .json -> .json.migrated.
    """
    row = conn.execute(
        "SELECT value FROM metadata WHERE key = 'migrated_at'"
    ).fetchone()
    if row is not None:
        return

    tokens_path = os.path.join(tracking_dir, "tokens.json")
    agents_path = os.path.join(tracking_dir, "agents.json")

    if os.path.exists(tokens_path):
        try:
            with open(tokens_path, encoding="utf-8") as f:
                data = json.load(f)
            if data:
                _insert_turns(conn, data)
        except (json.JSONDecodeError, OSError):
            pass

    if os.path.exists(agents_path):
        try:
            with open(agents_path, encoding="utf-8") as f:
                data = json.load(f)
            if data:
                _insert_agents(conn, data)
        except (json.JSONDecodeError, OSError):
            pass

    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
        ("schema_version", "1"),
    )
    conn.execute(
        "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
        ("migrated_at", now),
    )
    conn.commit()

    # Rename originals so migration won't re-run even without the metadata check
    for path in (tokens_path, agents_path):
        if os.path.exists(path):
            try:
                os.rename(path, path + ".migrated")
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Core DB access
# ---------------------------------------------------------------------------

def init_db(tracking_dir: str) -> None:
    """Create the database and tables. Safe to call repeatedly."""
    os.makedirs(tracking_dir, exist_ok=True)
    path = _db_path(tracking_dir)
    conn = sqlite3.connect(path)
    try:
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()


def get_db(tracking_dir: str) -> sqlite3.Connection:
    """Open (or create) the database and return a connection.

    Sets row_factory=Row, WAL mode, synchronous=NORMAL, and runs migration
    if needed. Caller should use as context manager: ``with get_db(d) as conn:``.
    """
    path = _db_path(tracking_dir)
    if not os.path.exists(path):
        init_db(tracking_dir)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError:
        conn.execute("PRAGMA journal_mode=DELETE")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA_SQL)
    _maybe_migrate(conn, tracking_dir)
    return conn


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def upsert_turns(tracking_dir: str, entries: list[dict]) -> int:
    """INSERT OR REPLACE turn entries. Returns number of rows affected."""
    with get_db(tracking_dir) as conn:
        _insert_turns(conn, entries)
        conn.commit()
    return len(entries)


def append_agent(tracking_dir: str, entry: dict) -> None:
    """Append a single agent entry."""
    with get_db(tracking_dir) as conn:
        _insert_agents(conn, [entry])
        conn.commit()


def get_all_turns(tracking_dir: str) -> list[dict]:
    """Return all turn rows as dicts, ordered by date, session_id, turn_index."""
    with get_db(tracking_dir) as conn:
        rows = conn.execute(
            "SELECT * FROM turns ORDER BY date, session_id, turn_index"
        ).fetchall()
    return [dict(r) for r in rows]


def get_all_agents(tracking_dir: str) -> list[dict]:
    """Return all agent rows as dicts (without the autoincrement id), ordered by id."""
    with get_db(tracking_dir) as conn:
        rows = conn.execute("SELECT * FROM agents ORDER BY id").fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d.pop("id", None)
        result.append(d)
    return result


def replace_session_skills(
    tracking_dir: str, session_id: str, entries: list[dict]
) -> None:
    """Delete all skills for a session and insert replacements atomically."""
    with get_db(tracking_dir) as conn:
        conn.execute("DELETE FROM skills WHERE session_id = ?", (session_id,))
        _insert_skills(conn, entries)
        conn.commit()


def get_all_skills(tracking_dir: str) -> list[dict]:
    """Return all skill rows as dicts (without the autoincrement id), ordered by id."""
    with get_db(tracking_dir) as conn:
        rows = conn.execute("SELECT * FROM skills ORDER BY id").fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d.pop("id", None)
        result.append(d)
    return result


def count_turns_for_session(tracking_dir: str, session_id: str) -> int:
    """Return the number of turns for a given session."""
    with get_db(tracking_dir) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM turns WHERE session_id = ?", (session_id,)
        ).fetchone()
    return row[0]


def replace_session_turns(
    tracking_dir: str, session_id: str, entries: list[dict]
) -> None:
    """Delete all turns for a session and insert replacements atomically."""
    with get_db(tracking_dir) as conn:
        conn.execute("DELETE FROM turns WHERE session_id = ?", (session_id,))
        _insert_turns(conn, entries)
        conn.commit()


def patch_turn_duration(
    tracking_dir: str, session_id: str, turn_index: int, duration: int
) -> None:
    """Update duration_seconds for a specific turn."""
    with get_db(tracking_dir) as conn:
        conn.execute(
            "UPDATE turns SET duration_seconds = ? "
            "WHERE session_id = ? AND turn_index = ?",
            (duration, session_id, turn_index),
        )
        conn.commit()


def get_session_turns(tracking_dir: str, session_id: str) -> list[dict]:
    """Return turns for a specific session, ordered by turn_index."""
    with get_db(tracking_dir) as conn:
        rows = conn.execute(
            "SELECT * FROM turns WHERE session_id = ? ORDER BY turn_index",
            (session_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def export_json(
    tracking_dir: str,
    tokens_path: Optional[str] = None,
    agents_path: Optional[str] = None,
) -> None:
    """Export turns and/or agents tables to JSON files."""
    if tokens_path is not None:
        data = get_all_turns(tracking_dir)
        with open(tokens_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")

    if agents_path is not None:
        data = get_all_agents(tracking_dir)
        with open(agents_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] != "--init":
        print(f"Usage: {sys.argv[0]} --init <tracking_dir>", file=sys.stderr)
        sys.exit(1)
    init_db(sys.argv[2])
    print(f"Initialized {os.path.join(sys.argv[2], DB_NAME)}")
