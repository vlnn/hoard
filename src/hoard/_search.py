from __future__ import annotations

import sqlite3
from typing import Optional

LIMIT = 40
EVERYTHING = -1

NEWEST = "mtime DESC"
PICTURED_FIRST = "icon IS NULL, mtime DESC"

ENTITIES = """
SELECT e.id, e.title, e.fields_json, e.icon
FROM ({chosen}) chosen JOIN entities e ON e.rowid = chosen.rowid
ORDER BY {order}
"""

MATCHING = "rowid IN (SELECT rowid FROM fts WHERE fts MATCH ?)"

HELD = "EXISTS (SELECT 1 FROM sightings s WHERE s.id = entities.id AND s.storage = ?)"

UNTAGGED = "NOT EXISTS (SELECT 1 FROM tags t WHERE t.id = entities.id)"

RANDOM = "SELECT rowid FROM entities ORDER BY random() LIMIT ?"

BY_ID = "SELECT id, title, fields_json, icon FROM entities WHERE id = ?"


def search_words(typed: str) -> list:
    return [word for word in typed.split() if any(c.isalnum() for c in word)]


def quoted_prefix(word: str) -> str:
    return '"' + word.replace('"', '""') + '"*'


def match_expression(typed: str) -> str:
    return " ".join(quoted_prefix(word) for word in search_words(typed))


def split_command(typed: str) -> tuple:
    words = typed.split()
    return (words[0].lower(), words[1:]) if words else ("", [])


def is_empty(con: sqlite3.Connection) -> bool:
    return con.execute("SELECT 1 FROM entities LIMIT 1").fetchone() is None


def order_of(kind) -> str:
    return PICTURED_FIRST if kind.pictured_first else NEWEST


def chosen(con: sqlite3.Connection, chooser: str, *parameters, order: str = NEWEST) -> list:
    return con.execute(ENTITIES.format(chosen=chooser, order=order), parameters).fetchall()


def where(typed: str, on=(), off=(), untagged: bool = False) -> Optional[tuple]:
    clauses, parameters = [], []
    if typed.strip():
        expression = match_expression(typed)
        if not expression:
            return None
        clauses.append(MATCHING)
        parameters.append(expression)
    for storage in on:
        clauses.append(HELD)
        parameters.append(storage)
    for storage in off:
        clauses.append(f"NOT {HELD}")
        parameters.append(storage)
    if untagged:
        clauses.append(UNTAGGED)
    return (" WHERE " + " AND ".join(clauses) if clauses else "", tuple(parameters))


def search(con: sqlite3.Connection, typed: str, limit: int = LIMIT, on=(), off=(), untagged: bool = False, order: str = NEWEST) -> list:
    narrowed = where(typed, on, off, untagged)
    if narrowed is None:
        return []
    clause, parameters = narrowed
    return chosen(con, f"SELECT rowid FROM entities{clause} ORDER BY {order} LIMIT ?", *parameters, limit, order=order)


def count(con: sqlite3.Connection, typed: str, on=(), off=(), untagged: bool = False) -> int:
    narrowed = where(typed, on, off, untagged)
    if narrowed is None:
        return 0
    clause, parameters = narrowed
    return con.execute(f"SELECT count(*) FROM entities{clause}", parameters).fetchone()[0]


def ids(con: sqlite3.Connection, typed: str, on=(), off=(), untagged: bool = False, order: str = NEWEST) -> list:
    narrowed = where(typed, on, off, untagged)
    if narrowed is None:
        return []
    clause, parameters = narrowed
    return [row[0] for row in con.execute(f"SELECT id FROM entities{clause} ORDER BY {order}", parameters)]


def random_entities(con: sqlite3.Connection, limit: int) -> list:
    return chosen(con, RANDOM, limit)


def by_ids(con: sqlite3.Connection, ids) -> list:
    found = (con.execute(BY_ID, (entity_id,)).fetchone() for entity_id in dict.fromkeys(ids))
    return [row for row in found if row]
