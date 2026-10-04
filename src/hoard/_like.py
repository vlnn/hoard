from __future__ import annotations

import sqlite3
from typing import Optional

from hoard import _embed, _fold, _rows, _search, _vectors
from hoard.contract import Context, Kind
from hoard.items import Head

NEIGHBOURS = "SELECT other, score FROM neighbours WHERE model = ? AND id = ? ORDER BY rank"


def newest_id(con: sqlite3.Connection) -> Optional[str]:
    rows = _search.search(con, "", 1)
    return rows[0][0] if rows else None


def seed_of(con: sqlite3.Connection, kind: Kind, ctx: Context, words: list) -> Optional[str]:
    if words and words[0].startswith("#"):
        return words[0][1:]
    if words:
        hits = _search.search(con, " ".join(words), 1)
        return hits[0][0] if hits else None
    remembered = kind.last_opened(ctx) if kind.last_opened else None
    return remembered or newest_id(con)


def title_of(con: sqlite3.Connection, entity_id: str) -> Optional[str]:
    row = con.execute("SELECT title FROM entities WHERE id = ?", (entity_id,)).fetchone()
    return row[0] if row else None


def embed_head(con: sqlite3.Connection, kind: Kind, key: str) -> list:
    if _embed.is_local(kind):
        return []
    waiting = len(_vectors.missing(con, key))
    if not waiting:
        return []
    return [Head("embed", f"Embed {waiting} new", "the model runs in the background", verb="embed", arg="embed:")]


def neighbour_items(con, kind: Kind, ctx: Context, key: str, seed: str, title: str) -> list:
    scores = dict(con.execute(NEIGHBOURS, (key, seed)).fetchall())
    rows = _fold.fold(con, kind, ctx, _search.by_ids(con, list(scores)))
    kept = [row for row in rows if row.found.entity.title.casefold() != title.casefold()]
    items = []
    for row in kept:
        item = _rows.entity_item(kind, row, ctx=ctx)
        items.append(item._replace(subtitle=f"{round(scores[item.id] * 100)}% · {item.subtitle}"))
    return items


def like_rows(con, kind: Kind, ctx: Context, words: list) -> tuple:
    key = _embed.model_key(con, kind)
    heads = embed_head(con, kind, key)
    seed = seed_of(con, kind, ctx, words)
    title = title_of(con, seed) if seed else None
    if title is None:
        return tuple(heads) + (Head("none", "Nothing to start from"),)
    if not _vectors.has_vector(con, key, seed):
        return tuple(heads) + (Head("none", f"{title} has no vector yet"),)
    items = neighbour_items(con, kind, ctx, key, seed, title)
    seed_head = Head("seed", f"Like {title}", neighbour_count(len(items)))
    return tuple(heads) + (seed_head,) + tuple(items)


def neighbour_count(count: int) -> str:
    return f"{count} neighbour" if count == 1 else f"{count} neighbours"
