from __future__ import annotations

import json
import sqlite3
from typing import NamedTuple, Optional

from hoard import _answers, _search
from hoard._questions import NAME, confident
from hoard._text import refresh_text
from hoard.contract import Change, Kind

ANSWERED = """
SELECT e.id, e.title, e.fields_json, a.answer_json FROM entities e
JOIN answers a ON a.id = e.id AND a.question = 'name' AND a.evidence_hash = e.evidence_hash
"""


class Suggestion(NamedTuple):
    id: str
    title: str
    fields: tuple
    answer: dict


def overlaid(kind: Kind, title: str, fields: tuple, answer: dict) -> tuple:
    named = list(fields)
    for field in kind.nameable:
        value = str(answer.get(field) or "").strip()
        if value:
            named[kind.fields.index(field)] = value
    return (str(answer.get("title") or "").strip() or title, tuple(named))


def stored(con: sqlite3.Connection, entity_id: str) -> tuple:
    title, fields_json, evidence_hash = con.execute(
        "SELECT title, fields_json, evidence_hash FROM entities WHERE id = ?", (entity_id,)
    ).fetchone()
    return title, tuple(json.loads(fields_json)), evidence_hash


def write(con: sqlite3.Connection, entity_id: str, title: str, fields: tuple) -> None:
    con.execute(
        "UPDATE entities SET title = ?, fields_json = ? WHERE id = ?",
        (title, json.dumps(list(fields), ensure_ascii=False), entity_id),
    )


def overlay(con: sqlite3.Connection, kind: Kind, entity_id: str) -> None:
    if not kind.nameable:
        return
    title, fields, evidence_hash = stored(con, entity_id)
    answer = _answers.fresh(con, entity_id, NAME, evidence_hash)
    if answer and confident(answer):
        write(con, entity_id, *overlaid(kind, title, fields, answer))


def answered(con: sqlite3.Connection, typed: str) -> list:
    narrowed = _search.where(typed)
    if narrowed is None:
        return []
    clause, parameters = narrowed
    scope = f" WHERE e.rowid IN (SELECT rowid FROM entities{clause})" if clause else ""
    return con.execute(ANSWERED + scope + " ORDER BY e.mtime DESC", parameters).fetchall()


def pending(con: sqlite3.Connection, kind: Kind, typed: str = "") -> list:
    found = []
    for entity_id, title, fields_json, answer_json in answered(con, typed):
        fields, answer = tuple(json.loads(fields_json)), json.loads(answer_json)
        if not confident(answer) and overlaid(kind, title, fields, answer) != (title, fields):
            found.append(Suggestion(entity_id, title, fields, answer))
    return found


def store_answer(con: sqlite3.Connection, entity_id: str, answer: Optional[dict]) -> None:
    if answer is not None:
        con.execute(
            "UPDATE answers SET answer_json = ? WHERE id = ? AND question = ?",
            (json.dumps(answer, ensure_ascii=False), entity_id, NAME),
        )


def accept(con: sqlite3.Connection, kind: Kind, suggestions: list) -> list:
    changes = []
    for suggestion in suggestions:
        accepted = {**suggestion.answer, "accepted": True}
        before = {"title": suggestion.title, "fields": list(suggestion.fields), "answer": suggestion.answer}
        store_answer(con, suggestion.id, accepted)
        write(con, suggestion.id, *overlaid(kind, suggestion.title, suggestion.fields, accepted))
        refresh_text(con, suggestion.id)
        changes.append(Change(suggestion.id, "name", before, accepted))
    return changes


def undo(con: sqlite3.Connection, changes, ctx) -> None:
    for change in changes:
        write(con, change.id, change.before["title"], tuple(change.before["fields"]))
        store_answer(con, change.id, change.before["answer"])
        refresh_text(con, change.id)
