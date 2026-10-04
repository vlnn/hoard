from __future__ import annotations

import sqlite3

from hoard import _answers, _embedder, _models, _neighbours, _vectors
from hoard._http import ModelError
from hoard.contract import Context, Kind

DEFAULT_MODEL = "default"
BATCH = 16


def embeddings_server(con: sqlite3.Connection, ctx: Context) -> _models.Server:
    server = _models.server(con, ctx, "embeddings")
    if server is None:
        raise ModelError("no embeddings server is set")
    return server


def model_key(con: sqlite3.Connection, ctx: Context) -> str:
    return _models.model_of(con, "embeddings") or DEFAULT_MODEL


def logger(con: sqlite3.Connection):
    return lambda kind_of, sent, received: _answers.record_exchange(con, kind_of, sent, received)


def embed_batch(con: sqlite3.Connection, kind: Kind, server, key: str, batch: list) -> None:
    texts = [kind.like.text(evidence) for _, evidence in batch]
    for (entity_id, _), vector in zip(batch, _embedder.embed(server.url, server.model, texts, log=logger(con), key=server.key)):
        unit = _vectors.normalized(vector)
        _vectors.store(con, key, entity_id, unit)
        _neighbours.insert(con, key, entity_id, unit)
    con.commit()


def run(con: sqlite3.Connection, kind: Kind, ctx: Context) -> int:
    if kind.like is None:
        return 0
    server, key = embeddings_server(con, ctx), model_key(con, ctx)
    waiting = _vectors.missing(con, key)
    for start in range(0, len(waiting), BATCH):
        embed_batch(con, kind, server, key, waiting[start : start + BATCH])
    return len(waiting)
