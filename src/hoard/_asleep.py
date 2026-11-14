from __future__ import annotations

import json
import sqlite3

from hoard.contract import Context, Kind

WHOLLY_REACHED = "SELECT storage, roots_json FROM storage_state WHERE roots_json IS NOT NULL AND roots_json = reach_json"


def wholly_reached(con: sqlite3.Connection) -> dict:
    return {storage: tuple(json.loads(roots_json)) for storage, roots_json in con.execute(WHOLLY_REACHED)}


def left_asleep(con: sqlite3.Connection, kind: Kind) -> dict:
    reached = wholly_reached(con)
    return {storage.name: reached[storage.name] for storage in kind.storages if storage.sleeps and storage.name in reached}


def roots_of(storage, ctx: Context, asleep: dict) -> tuple:
    return asleep[storage.name] if storage.name in asleep else tuple(storage.roots(ctx))


def context(con: sqlite3.Connection, kind: Kind, ctx: Context) -> Context:
    asleep = left_asleep(con, kind)
    return ctx._replace(roots={storage.name: roots_of(storage, ctx, asleep) for storage in kind.storages}, asleep=asleep)
