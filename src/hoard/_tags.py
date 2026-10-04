from __future__ import annotations

import sqlite3
import time
from typing import Optional

from hoard import _answers
from hoard._questions import TAG
from hoard._text import refresh_text
from hoard.contract import Change


def tags_of(con: sqlite3.Connection, entity_id: str) -> list:
    return [list(row) for row in con.execute("SELECT tag, set_by FROM tags WHERE id = ? ORDER BY tag", (entity_id,))]


def replace(con: sqlite3.Connection, entity_id: str, entries) -> None:
    con.execute("DELETE FROM tags WHERE id = ?", (entity_id,))
    con.executemany(
        "INSERT INTO tags(id, tag, set_by, set_at) VALUES (?, ?, ?, ?)",
        [(entity_id, tag, set_by, time.time()) for tag, set_by in entries],
    )
    refresh_text(con, entity_id)


def set_tag(con: sqlite3.Connection, entity_id: str, tag: str, set_by: str) -> Change:
    before = tags_of(con, entity_id)
    replace(con, entity_id, [(tag, set_by)])
    if set_by == "hand":
        _answers.forget(con, entity_id, TAG)
    return Change(entity_id, "tag", before, [[tag, set_by]])


def undo(con: sqlite3.Connection, changes, ctx) -> None:
    for change in reversed(list(changes)):
        replace(con, change.id, change.before)


def suggestion(con: sqlite3.Connection, entity_id: str) -> Optional[str]:
    (evidence_hash,) = con.execute("SELECT evidence_hash FROM entities WHERE id = ?", (entity_id,)).fetchone()
    answer = _answers.fresh(con, entity_id, TAG, evidence_hash or "")
    if not answer:
        return None
    return str(answer.get("tag") or "") or None
