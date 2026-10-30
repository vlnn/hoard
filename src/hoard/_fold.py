from __future__ import annotations

import json
import os
import sqlite3
from typing import NamedTuple, Optional

from hoard.contract import TAGS as TAGS_SUBJECT
from hoard.contract import Context, Entity, Found, Kind, Sighting

CHUNK = 500
WHOLE_TABLE = 2000
SIGHTINGS = "SELECT id, storage, locator, mtime, size FROM sightings"
TAGS = "SELECT id, tag FROM tags"
GUESSES = (
    "SELECT a.id, a.answer_json FROM answers a JOIN entities e ON e.id = a.id AND e.evidence_hash = a.evidence_hash"
    " WHERE a.question = 'tag'"
)


class Row(NamedTuple):
    found: Found
    icon: Optional[str]


def mounted_roots(kind: Kind, ctx: Context) -> dict:
    return {s.name: tuple(root for root in ctx.roots_of(s.name) if s.mounted(root)) for s in kind.storages}


def under(locator: str, root: str) -> bool:
    return locator == root or locator.startswith(root.rstrip(os.sep) + os.sep)


def real_roots(ctx: Context) -> list:
    return [os.path.realpath(root) for roots in ctx.roots.values() for root in roots]


def ground_of(kind: Kind, ctx: Context) -> list:
    wider = [os.path.realpath(folder) for folder in kind.ground(ctx)] if kind.ground else []
    return wider + real_roots(ctx)


def prefixes(mounted: dict) -> dict:
    return {storage: tuple(root.rstrip(os.sep) + os.sep for root in roots) for storage, roots in mounted.items()}


def is_reachable(storage: str, locator: Optional[str], reach: dict) -> bool:
    return locator is None or locator.startswith(reach.get(storage, ()))


def chunks(items: list, size: int = CHUNK):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def narrowed(query: str, column: str, count: int) -> str:
    glue = "AND" if " WHERE " in query else "WHERE"
    return f"{query} {glue} {column} IN ({','.join('?' * count)})"


def rows_for(con: sqlite3.Connection, query: str, ids: list, column: str = "id"):
    if len(ids) > WHOLE_TABLE:
        wanted = set(ids)
        return (row for row in con.execute(query) if row[0] in wanted)
    return (row for chunk in chunks(ids) for row in con.execute(narrowed(query, column, len(chunk)), chunk))


def sightings_of(con: sqlite3.Connection, ids: list) -> dict:
    found = {}
    for row in rows_for(con, SIGHTINGS, ids):
        found.setdefault(row[0], []).append(row)
    return found


def tags_of(con: sqlite3.Connection, ids: list) -> dict:
    found = {}
    for entity_id, tag in rows_for(con, TAGS, ids):
        found.setdefault(entity_id, []).append(tag)
    return {entity_id: tuple(sorted(tags)) for entity_id, tags in found.items()}


def guessed_tag(answer_json: str) -> str:
    return str(json.loads(answer_json).get("tag") or "")


def guesses_of(con: sqlite3.Connection, ids: list, ctx: Context) -> dict:
    found = {}
    for entity_id, answer_json in rows_for(con, GUESSES, ids, column="a.id"):
        if tag := guessed_tag(answer_json):
            found[entity_id] = ctx.standard(TAGS_SUBJECT, tag)
    return found


def sighting(row: tuple, reach: dict) -> Sighting:
    entity_id, storage, locator, mtime, size = row
    return Sighting(entity_id, storage, locator, mtime, size, is_reachable(storage, locator, reach))


def in_kind_order(order: dict, rows: list, reach: dict) -> tuple:
    if len(rows) > 1:
        rows = sorted(rows, key=lambda row: (order.get(row[1], len(order)), row[2] or ""))
    return tuple(sighting(row, reach) for row in rows)


def fold(con: sqlite3.Connection, kind: Kind, ctx: Context, entity_rows: list) -> list:
    reach = prefixes(mounted_roots(kind, ctx))
    order = {storage.name: n for n, storage in enumerate(kind.storages)}
    ids = [row[0] for row in entity_rows]
    sightings, tags, guesses = sightings_of(con, ids), tags_of(con, ids), guesses_of(con, ids, ctx)
    return [
        Row(
            Found(
                Entity(entity_id, title, tuple(json.loads(fields_json))),
                in_kind_order(order, sightings.get(entity_id, []), reach),
                tags.get(entity_id, ()),
                guesses.get(entity_id),
            ),
            icon,
        )
        for entity_id, title, fields_json, icon in entity_rows
    ]
