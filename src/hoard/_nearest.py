from __future__ import annotations

import heapq
import operator
import sqlite3
from array import array

from hoard import _signatures, _vectors

CANDIDATES = 200
SEED = "SELECT vec, sig FROM vectors WHERE model = ? AND id = ? AND sig IS NOT NULL"
SIGNED = "SELECT id, sig FROM vectors WHERE model = ? AND id != ? AND sig IS NOT NULL"


def dot(one: array, other: array) -> float:
    return sum(map(operator.mul, one, other))


def shortlist(con: sqlite3.Connection, model: str, seed: str, signature: bytes) -> list:
    origin, rows = _signatures.number(signature), con.execute(SIGNED, (model, seed))
    closest = heapq.nsmallest(CANDIDATES, ((_signatures.bits_apart(origin, sig), other) for other, sig in rows))
    return [other for _, other in closest]


def vectors_of(con: sqlite3.Connection, model: str, ids: list) -> list:
    marks = ",".join("?" * len(ids))
    rows = con.execute(f"SELECT id, vec FROM vectors WHERE model = ? AND id IN ({marks})", (model, *ids))
    return [(other, _vectors.unpacked(blob)) for other, blob in rows]


def nearest(con: sqlite3.Connection, model: str, seed: str) -> list:
    row = con.execute(SEED, (model, seed)).fetchone()
    if row is None:
        return []
    vector, signature = _vectors.unpacked(row[0]), row[1]
    scored = [(dot(vector, other_vector), other) for other, other_vector in vectors_of(con, model, shortlist(con, model, seed, signature))]
    return sorted(scored, reverse=True)
