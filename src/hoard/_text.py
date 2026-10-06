from __future__ import annotations

import json
import sqlite3


def searchable_body(con: sqlite3.Connection, entity_id: str, fields_json: str) -> str:
    derived = [value for (value,) in con.execute("SELECT value FROM derived WHERE id = ? ORDER BY key", (entity_id,))]
    tags = [tag for (tag,) in con.execute("SELECT tag FROM tags WHERE id = ? ORDER BY tag", (entity_id,))]
    return "\n".join(value for value in [*json.loads(fields_json), *derived, *tags] if value)


def refresh_text(con: sqlite3.Connection, entity_id: str) -> None:
    row = con.execute("SELECT rowid, title, fields_json FROM entities WHERE id = ?", (entity_id,)).fetchone()
    if row is None:
        return
    rowid, title, fields_json = row
    con.execute("DELETE FROM fts WHERE rowid = ?", (rowid,))
    con.execute(
        "INSERT INTO fts(rowid, id, title, body) VALUES (?, ?, ?, ?)",
        (rowid, entity_id, title, searchable_body(con, entity_id, fields_json)),
    )
