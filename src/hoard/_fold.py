from __future__ import annotations

import json
import os
import sqlite3
from typing import NamedTuple, Optional

from hoard.contract import Context, Entity, Found, Kind, Sighting

CHUNK = 500
WHOLE_TABLE = 2000
SIGHTINGS = "SELECT id, storage, locator, mtime, size FROM sightings"


class Row(NamedTuple):
    found: Found
    icon: Optional[str]


def mounted_roots(kind: Kind, ctx: Context) -> dict:
    return {s.name: tuple(root for root in ctx.roots_of(s.name) if s.mounted(root)) for s in kind.storages}


def under(locator: str, root: str) -> bool:
    return locator == root or locator.startswith(root.rstrip(os.sep) + os.sep)


def prefixes(mounted: dict) -> dict:
    return {storage: tuple(root.rstrip(os.sep) + os.sep for root in roots) for storage, roots in mounted.items()}


def is_reachable(storage: str, locator: Optional[str], reach: dict) -> bool:
    return locator is None or locator.startswith(reach.get(storage, ()))


def chunks(items: list, size: int = CHUNK):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def sighting_rows(con: sqlite3.Connection, ids: list):
    if len(ids) > WHOLE_TABLE:
        wanted = set(ids)
        return (row for row in con.execute(SIGHTINGS) if row[0] in wanted)
    return (row for chunk in chunks(ids) for row in con.execute(f"{SIGHTINGS} WHERE id IN ({','.join('?' * len(chunk))})", chunk))


def sightings_of(con: sqlite3.Connection, ids: list) -> dict:
    found = {}
    for row in sighting_rows(con, ids):
        found.setdefault(row[0], []).append(row)
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
    sightings = sightings_of(con, [row[0] for row in entity_rows])
    return [
        Row(
            Found(Entity(entity_id, title, tuple(json.loads(fields_json))), in_kind_order(order, sightings.get(entity_id, []), reach)),
            icon,
        )
        for entity_id, title, fields_json, icon in entity_rows
    ]
