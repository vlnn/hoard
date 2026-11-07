from __future__ import annotations

import json
import re
import sqlite3

LINK = "link"
LINKS = "SELECT variant, standard FROM standards WHERE set_by = ?"


def mentions(text: str, spelling: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(spelling)}(?!\w)", text) is not None


def linked_spellings(con: sqlite3.Connection, values: list) -> list:
    text = "\n".join(values)
    return [standard for variant, standard in con.execute(LINKS, (LINK,)) if mentions(text, variant)]


def searchable_body(con: sqlite3.Connection, entity_id: str, fields_json: str) -> str:
    derived = [value for (value,) in con.execute("SELECT value FROM derived WHERE id = ? ORDER BY key", (entity_id,))]
    tags = [tag for (tag,) in con.execute("SELECT tag FROM tags WHERE id = ? ORDER BY tag", (entity_id,))]
    own = [*json.loads(fields_json), *tags]
    return "\n".join(value for value in [*own, *derived, *linked_spellings(con, own)] if value)


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


def holders_of(con: sqlite3.Connection, spellings) -> list:
    found = {}
    for spelling in spellings:
        quoted = json.dumps(spelling, ensure_ascii=False)[1:-1]
        holders = con.execute("SELECT id FROM entities WHERE instr(fields_json, ?) > 0", (quoted,)).fetchall()
        tagged = con.execute("SELECT id FROM tags WHERE tag = ?", (spelling,)).fetchall()
        found.update(dict.fromkeys(entity_id for (entity_id,) in [*holders, *tagged]))
    return list(found)


def relinked(con: sqlite3.Connection, spellings) -> None:
    for entity_id in holders_of(con, spellings):
        refresh_text(con, entity_id)
        con.execute("DELETE FROM vectors WHERE id = ?", (entity_id,))
