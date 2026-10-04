from __future__ import annotations

import os
import sqlite3
from typing import Optional

SCHEMA_V1 = """
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE entities(
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    fields_json TEXT NOT NULL,
    icon TEXT,
    size INTEGER,
    mtime REAL,
    text_hash TEXT,
    first_seen INTEGER,
    last_seen INTEGER
);
CREATE INDEX entities_newest ON entities(mtime DESC);

CREATE TABLE sightings(
    id TEXT NOT NULL,
    storage TEXT NOT NULL,
    locator TEXT,
    mtime REAL,
    size INTEGER,
    PRIMARY KEY(id, storage)
);
CREATE INDEX sightings_locator ON sightings(storage, locator);

CREATE VIRTUAL TABLE fts USING fts5(
    id UNINDEXED, title, body,
    tokenize = 'unicode61 remove_diacritics 2'
);

CREATE TABLE derived(
    id TEXT, key TEXT, value TEXT, source TEXT, made_at REAL,
    PRIMARY KEY(id, key)
);

CREATE TABLE storage_state(
    storage TEXT PRIMARY KEY,
    mounted INTEGER,
    checked_at REAL,
    last_update_at REAL,
    count INTEGER
);

CREATE TABLE tags(
    id TEXT, tag TEXT, set_by TEXT, set_at REAL,
    PRIMARY KEY(id, tag)
);

CREATE TABLE answers(
    id TEXT, question TEXT, evidence_hash TEXT, model TEXT, answer_json TEXT, asked_at REAL,
    PRIMARY KEY(id, question)
);

CREATE TABLE vectors(
    model TEXT, id TEXT, vec BLOB,
    PRIMARY KEY(model, id)
);

CREATE TABLE neighbours(
    model TEXT, id TEXT, rank INTEGER, other TEXT, score REAL,
    PRIMARY KEY(model, id, rank)
);

CREATE TABLE journal(
    batch INTEGER, seq INTEGER, verb TEXT, id TEXT,
    before_json TEXT, after_json TEXT, at REAL, undoable INTEGER,
    PRIMARY KEY(batch, seq)
);

CREATE TABLE exchanges(at REAL, kind_of TEXT, request TEXT, response TEXT);
"""

JOURNAL_KIND_OF_CHANGE = "ALTER TABLE journal ADD COLUMN kind_of_change TEXT;"

MIGRATIONS = (SCHEMA_V1, JOURNAL_KIND_OF_CHANGE)

CACHE_TABLES = frozenset({"entities", "sightings", "fts", "derived", "storage_state"})
STORE_TABLES = frozenset({"tags", "answers", "vectors", "neighbours", "journal", "exchanges"})
KEPT_TABLES = STORE_TABLES | {"derived"}
REBUILT_TABLES = CACHE_TABLES - {"derived"}


def path_for(name: str, data: str) -> str:
    return os.path.join(data, f"{name}.sqlite")


def connect(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(path, timeout=5)
    migrate(con)
    return con


def meta(con: sqlite3.Connection, key: str, default: Optional[str] = None) -> Optional[str]:
    row = con.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_meta(con: sqlite3.Connection, key: str, value: str) -> None:
    con.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", (key, value))


def schema_version(con: sqlite3.Connection) -> int:
    try:
        return int(meta(con, "schema_version", "0"))
    except sqlite3.OperationalError:
        return 0


def migrate(con: sqlite3.Connection) -> None:
    current = schema_version(con)
    if current == len(MIGRATIONS):
        return
    if current == 0:
        con.execute("PRAGMA journal_mode = WAL")
    for version, script in enumerate(MIGRATIONS[current:], current + 1):
        con.executescript(script)
        set_meta(con, "schema_version", str(version))
    con.commit()


def drop_cache(con: sqlite3.Connection) -> None:
    for table in sorted(REBUILT_TABLES):
        con.execute(f"DELETE FROM {table}")
