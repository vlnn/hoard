from __future__ import annotations

import math
import sqlite3
from array import array
from typing import Optional

from hoard import _signatures

MISSING = """
SELECT e.id, e.evidence FROM entities e
WHERE e.evidence IS NOT NULL AND e.evidence != ''
  AND NOT EXISTS (SELECT 1 FROM vectors v WHERE v.model = ? AND v.id = e.id AND v.sig IS NOT NULL)
ORDER BY e.mtime DESC
"""


WITHOUT_VECTOR = """
SELECT e.id, e.title, e.fields_json, e.icon FROM entities e
WHERE NOT EXISTS (SELECT 1 FROM vectors v WHERE v.model = ? AND v.id = e.id AND v.sig IS NOT NULL)
ORDER BY e.mtime DESC
"""


def without_vector(con: sqlite3.Connection, model: str) -> list:
    return con.execute(WITHOUT_VECTOR, (model,)).fetchall()


def normalized(vector: array) -> array:
    norm = math.sqrt(sum(x * x for x in vector))
    return array("f", (x / norm for x in vector)) if norm else array("f", vector)


def packed(vector: array) -> bytes:
    return vector.tobytes()


def unpacked(blob: bytes) -> array:
    vector = array("f")
    vector.frombytes(blob)
    return vector


def store(con: sqlite3.Connection, model: str, entity_id: str, vector: array) -> None:
    signature = _signatures.of(vector)
    con.execute("INSERT OR REPLACE INTO vectors(model, id, vec, sig) VALUES (?, ?, ?, ?)", (model, entity_id, packed(vector), signature))


def missing(con: sqlite3.Connection, model: str) -> list:
    return con.execute(MISSING, (model,)).fetchall()


def has_vector(con: sqlite3.Connection, model: str, entity_id: str) -> bool:
    return con.execute("SELECT 1 FROM vectors WHERE model = ? AND id = ? AND sig IS NOT NULL", (model, entity_id)).fetchone() is not None


def every(con: sqlite3.Connection, model: str):
    for entity_id, blob in con.execute("SELECT id, vec FROM vectors WHERE model = ?", (model,)):
        yield entity_id, unpacked(blob)


def vector_of(con: sqlite3.Connection, model: str, entity_id: str) -> Optional[array]:
    row = con.execute("SELECT vec FROM vectors WHERE model = ? AND id = ?", (model, entity_id)).fetchone()
    return unpacked(row[0]) if row else None
