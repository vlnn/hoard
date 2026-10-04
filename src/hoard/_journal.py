from __future__ import annotations

import json
import sqlite3
import time
from typing import NamedTuple, Optional

from hoard.contract import Change


class Batch(NamedTuple):
    number: int
    verb: str
    changes: tuple
    at: float


def next_batch(con: sqlite3.Connection) -> int:
    (last,) = con.execute("SELECT coalesce(max(batch), 0) FROM journal").fetchone()
    return last + 1


def record(con: sqlite3.Connection, verb: str, changes, undoable: bool) -> int:
    number, now = next_batch(con), time.time()
    con.executemany(
        """
        INSERT INTO journal(batch, seq, verb, id, kind_of_change, before_json, after_json, at, undoable)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (number, seq, verb, c.id, c.kind_of_change, json.dumps(c.before), json.dumps(c.after), now, int(undoable))
            for seq, c in enumerate(changes)
        ],
    )
    return number


def last_undoable(con: sqlite3.Connection) -> Optional[Batch]:
    row = con.execute(
        "SELECT batch FROM journal GROUP BY batch HAVING min(undoable) = 1 ORDER BY batch DESC LIMIT 1"
    ).fetchone()
    return read_batch(con, row[0]) if row else None


def as_change(row: tuple) -> Change:
    entity_id, kind_of_change, before_json, after_json = row
    return Change(entity_id, kind_of_change, json.loads(before_json), json.loads(after_json))


def read_batch(con: sqlite3.Connection, number: int) -> Batch:
    rows = con.execute(
        "SELECT verb, at, id, kind_of_change, before_json, after_json FROM journal WHERE batch = ? ORDER BY seq",
        (number,),
    ).fetchall()
    return Batch(number, rows[0][0], tuple(as_change(row[2:]) for row in rows), rows[0][1])


def forget(con: sqlite3.Connection, number: int) -> None:
    con.execute("DELETE FROM journal WHERE batch = ?", (number,))
