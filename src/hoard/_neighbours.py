from __future__ import annotations

import operator
import sqlite3
from array import array

from hoard import _vectors

TOP = 20


def dot(one: array, other: array) -> float:
    return sum(map(operator.mul, one, other))


def write(con: sqlite3.Connection, model: str, entity_id: str, ranked: list) -> None:
    con.execute("DELETE FROM neighbours WHERE model = ? AND id = ?", (model, entity_id))
    con.executemany(
        "INSERT INTO neighbours(model, id, rank, other, score) VALUES (?, ?, ?, ?, ?)",
        [(model, entity_id, rank, other, score) for rank, (score, other) in enumerate(ranked)],
    )


def current(con: sqlite3.Connection, model: str, entity_id: str) -> list:
    rows = con.execute("SELECT score, other FROM neighbours WHERE model = ? AND id = ? ORDER BY rank", (model, entity_id))
    return [tuple(row) for row in rows]


def floors(con: sqlite3.Connection, model: str) -> dict:
    rows = con.execute("SELECT id, count(*), min(score) FROM neighbours WHERE model = ? GROUP BY id", (model,))
    return {entity_id: (count, lowest) for entity_id, count, lowest in rows}


def ranks_in(score: float, floor, top: int) -> bool:
    return floor is None or floor[0] < top or score > floor[1]


def adopt(con: sqlite3.Connection, model: str, entity_id: str, newcomer: str, score: float, top: int) -> None:
    kept = [entry for entry in current(con, model, entity_id) if entry[1] != newcomer]
    write(con, model, entity_id, sorted(kept + [(score, newcomer)], reverse=True)[:top])


def insert(con: sqlite3.Connection, model: str, entity_id: str, vector: array, top: int = TOP) -> None:
    scored = [(dot(vector, other_vector), other) for other, other_vector in _vectors.every(con, model) if other != entity_id]
    write(con, model, entity_id, sorted(scored, reverse=True)[:top])
    known = floors(con, model)
    for score, other in scored:
        if ranks_in(score, known.get(other), top):
            adopt(con, model, other, entity_id, score, top)
