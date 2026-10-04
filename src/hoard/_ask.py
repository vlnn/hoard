from __future__ import annotations

import json
import sqlite3
from typing import Optional

from hoard import _answers, _models, _names, _oracle, _questions
from hoard._http import ModelError
from hoard._text import refresh_text
from hoard.contract import Context, Kind


def chat_server(con: sqlite3.Connection, ctx: Context) -> _models.Server:
    server = _models.server(con, ctx, "chat")
    if server is None:
        raise ModelError("no chat model server is set")
    return server


def asked(kind: Kind, ctx: Context, questions: Optional[list]) -> list:
    on = _questions.enabled(kind, ctx)
    return [question for question in (questions or on) if question in on]


def evidence(con: sqlite3.Connection, entity_id: str) -> tuple:
    return con.execute("SELECT evidence, evidence_hash FROM entities WHERE id = ?", (entity_id,)).fetchone()


def logger(con: sqlite3.Connection):
    return lambda kind_of, sent, received: _answers.record_exchange(con, kind_of, sent, received)


def ask_one(con, kind: Kind, ctx: Context, server, question: str, entity_id: str) -> bool:
    text, digest = evidence(con, entity_id)
    schema = _questions.schema(kind, ctx, question)
    answer = _oracle.ask(server.url, server.model, _questions.text(kind, question), text, schema, log=logger(con), key=server.key)
    if answer is None:
        return False
    _answers.store(con, entity_id, question, digest, server.model, answer)
    if question == _questions.NAME:
        _names.overlay(con, kind, entity_id)
        refresh_text(con, entity_id)
    con.commit()
    return True


def run(con: sqlite3.Connection, kind: Kind, ctx: Context, questions: Optional[list] = None) -> int:
    server = chat_server(con, ctx)
    answered = 0
    for question in asked(kind, ctx, questions):
        for entity_id, _ in _answers.stale(con, question):
            answered += ask_one(con, kind, ctx, server, question, entity_id)
    return answered


def dry_run(con: sqlite3.Connection, kind: Kind, ctx: Context, questions: Optional[list] = None) -> list:
    lines = []
    for question in asked(kind, ctx, questions):
        lines.append(f"{question}: {_questions.text(kind, question)}")
        lines.append("schema: " + json.dumps(_questions.schema(kind, ctx, question), ensure_ascii=False))
        for entity_id, title in _answers.stale(con, question):
            lines += [f"— {title}", evidence(con, entity_id)[0], ""]
    return lines
