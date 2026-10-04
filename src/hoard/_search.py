from __future__ import annotations

import sqlite3

LIMIT = 40

ROWS = """
SELECT e.id, e.title, e.fields_json, e.icon,
       (SELECT s.locator FROM sightings s WHERE s.id = e.id ORDER BY s.mtime DESC LIMIT 1)
FROM ({chosen}) chosen JOIN entities e ON e.rowid = chosen.rowid
ORDER BY e.mtime DESC
"""

NEWEST = "SELECT rowid FROM entities ORDER BY mtime DESC LIMIT ?"

MATCHING = """
SELECT rowid FROM entities
WHERE rowid IN (SELECT rowid FROM fts WHERE fts MATCH ?)
ORDER BY mtime DESC LIMIT ?
"""


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


def newest(con: sqlite3.Connection, limit: int = LIMIT) -> list:
    return con.execute(ROWS.format(chosen=NEWEST), (limit,)).fetchall()


def matching(con: sqlite3.Connection, typed: str, limit: int = LIMIT) -> list:
    expression = match_expression(typed)
    if not expression:
        return []
    return con.execute(ROWS.format(chosen=MATCHING), (expression, limit)).fetchall()


def search(con: sqlite3.Connection, typed: str) -> list:
    return matching(con, typed) if typed.strip() else newest(con)
