from __future__ import annotations

import sqlite3
import sys
from array import array

from hoard import _answers, _fold, _models, _vectors
from hoard.contract import Context, Kind, LocalVectors

LOCAL_PREFIX = "local:"

DEFAULT_MODEL = "default"
BATCH = 16


def embeddings_server(con: sqlite3.Connection, ctx: Context) -> _models.Server:
    from hoard._http import ModelError

    server = _models.server(con, ctx, "embeddings")
    if server is None:
        raise ModelError("no embeddings server is set")
    return server


def is_local(kind: Kind) -> bool:
    return isinstance(kind.like, LocalVectors)


def model_key(con: sqlite3.Connection, kind: Kind) -> str:
    if is_local(kind):
        return LOCAL_PREFIX + kind.like.name
    return _models.model_of(con, "embeddings") or DEFAULT_MODEL


def local_vector(kind: Kind, found, ctx: Context):
    try:
        return array("f", kind.like.vector(found, ctx))
    except Exception as error:
        print(f"like {kind.like.name}: {found.entity.title}: {error!r}", file=sys.stderr)
        return None


def run_local(con: sqlite3.Connection, kind: Kind, ctx: Context) -> int:
    key, made = model_key(con, kind), 0
    for row in _fold.fold(con, kind, ctx, _vectors.without_vector(con, key)):
        vector = local_vector(kind, row.found, ctx)
        if vector is None:
            continue
        _vectors.store(con, key, row.found.entity.id, _vectors.normalized(vector))
        made += 1
    con.commit()
    return made


def logger(con: sqlite3.Connection):
    return lambda kind_of, sent, received: _answers.record_exchange(con, kind_of, sent, received)


def embed_batch(con: sqlite3.Connection, kind: Kind, server, key: str, batch: list) -> None:
    from hoard import _embedder

    texts = [kind.like.text(evidence) for _, evidence in batch]
    for (entity_id, _), vector in zip(batch, _embedder.embed(server.url, server.model, texts, log=logger(con), key=server.key)):
        _vectors.store(con, key, entity_id, _vectors.normalized(vector))
    con.commit()


def run(con: sqlite3.Connection, kind: Kind, ctx: Context) -> int:
    if kind.like is None:
        return 0
    if is_local(kind):
        return run_local(con, kind, ctx)
    server, key = embeddings_server(con, ctx), model_key(con, kind)
    waiting = _vectors.missing(con, key)
    for start in range(0, len(waiting), BATCH):
        embed_batch(con, kind, server, key, waiting[start : start + BATCH])
    return len(waiting)
