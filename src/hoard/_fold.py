from __future__ import annotations

import json
import os
import sqlite3
from typing import NamedTuple, Optional

from hoard.contract import Context, Entity, Found, Kind, Sighting

CHUNK = 500


class Row(NamedTuple):
    found: Found
    icon: Optional[str]


def mounted_roots(kind: Kind, ctx: Context) -> dict:
    return {s.name: tuple(root for root in ctx.roots_of(s.name) if s.mounted(root)) for s in kind.storages}


def under(locator: str, root: str) -> bool:
    return locator == root or locator.startswith(root.rstrip(os.sep) + os.sep)


def is_reachable(storage: str, locator: Optional[str], mounted: dict) -> bool:
    return locator is None or any(under(locator, root) for root in mounted.get(storage, ()))


def chunks(items: list, size: int = CHUNK):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def sightings_of(con: sqlite3.Connection, ids: list) -> dict:
    found = {}
    for chunk in chunks(ids):
        marks = ",".join("?" * len(chunk))
        rows = con.execute(f"SELECT id, storage, locator, mtime, size FROM sightings WHERE id IN ({marks})", chunk)
        for row in rows:
            found.setdefault(row[0], []).append(row)
    return found


def sighting(row: tuple, mounted: dict) -> Sighting:
    entity_id, storage, locator, mtime, size = row
    return Sighting(entity_id, storage, locator, mtime, size, is_reachable(storage, locator, mounted))


def in_kind_order(kind: Kind, rows: list, mounted: dict) -> tuple:
    order = {storage.name: n for n, storage in enumerate(kind.storages)}
    ordered = sorted(rows, key=lambda row: (order.get(row[1], len(order)), row[2] or ""))
    return tuple(sighting(row, mounted) for row in ordered)


def fold(con: sqlite3.Connection, kind: Kind, ctx: Context, entity_rows: list) -> list:
    mounted = mounted_roots(kind, ctx)
    sightings = sightings_of(con, [row[0] for row in entity_rows])
    return [
        Row(
            Found(Entity(entity_id, title, tuple(json.loads(fields_json))), in_kind_order(kind, sightings.get(entity_id, []), mounted)),
            icon,
        )
        for entity_id, title, fields_json, icon in entity_rows
    ]
