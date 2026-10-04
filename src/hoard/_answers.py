from __future__ import annotations

import json
import sqlite3
import time
from typing import Optional

EXCHANGES_KEPT = 300

STALE = """
SELECT e.id, e.title FROM entities e
LEFT JOIN answers a ON a.id = e.id AND a.question = ?
WHERE e.evidence IS NOT NULL AND e.evidence != '' AND (a.id IS NULL OR a.evidence_hash != e.evidence_hash)
ORDER BY e.mtime DESC
"""


def store(con: sqlite3.Connection, entity_id: str, question: str, evidence_hash: str, model: str, answer: dict) -> None:
    con.execute(
        "INSERT OR REPLACE INTO answers(id, question, evidence_hash, model, answer_json, asked_at) VALUES (?, ?, ?, ?, ?, ?)",
        (entity_id, question, evidence_hash, model, json.dumps(answer, ensure_ascii=False), time.time()),
    )


def fresh(con: sqlite3.Connection, entity_id: str, question: str, evidence_hash: str) -> Optional[dict]:
    row = con.execute(
        "SELECT answer_json FROM answers WHERE id = ? AND question = ? AND evidence_hash = ?",
        (entity_id, question, evidence_hash),
    ).fetchone()
    return json.loads(row[0]) if row else None


def stale(con: sqlite3.Connection, question: str) -> list:
    return con.execute(STALE, (question,)).fetchall()


def forget(con: sqlite3.Connection, entity_id: str, question: str) -> None:
    con.execute("DELETE FROM answers WHERE id = ? AND question = ?", (entity_id, question))


def record_exchange(con: sqlite3.Connection, kind_of: str, request, response, keep: int = EXCHANGES_KEPT) -> None:
    con.execute(
        "INSERT INTO exchanges(at, kind_of, request, response) VALUES (?, ?, ?, ?)",
        (time.time(), kind_of, json.dumps(request, ensure_ascii=False), json.dumps(response, ensure_ascii=False)),
    )
    con.execute(
        "DELETE FROM exchanges WHERE rowid NOT IN (SELECT rowid FROM exchanges ORDER BY at DESC, rowid DESC LIMIT ?)",
        (keep,),
    )
