from __future__ import annotations

import json
from functools import singledispatch

from hoard.items import Head, Item, Items, Mod


def mod_json(item_id: str, mod: Mod) -> dict:
    return {"arg": item_id, "subtitle": mod.subtitle, "valid": True, "variables": {"verb": mod.verb}}


@singledispatch
def row_json(row) -> dict:
    raise TypeError(f"cannot render {row!r}")


@row_json.register(Item)
def item_json(row: Item) -> dict:
    document = {
        "uid": row.id,
        "title": row.title,
        "subtitle": row.subtitle,
        "arg": row.id,
        "valid": True,
        "variables": {"verb": row.verb},
        "text": {"copy": row.locator or row.title, "largetype": row.title},
    }
    if row.icon:
        document["icon"] = {"path": row.icon}
    if row.locator:
        document["quicklookurl"] = row.locator
    if row.mods:
        document["mods"] = {mod.key: mod_json(row.id, mod) for mod in row.mods}
    return document


@row_json.register(Head)
def head_json(row: Head) -> dict:
    document = {
        "title": row.title,
        "subtitle": row.subtitle,
        "arg": f"batch:{row.batch}" if row.batch else f"head:{row.name}",
        "valid": row.verb is not None,
    }
    if row.verb is not None:
        document["variables"] = {"verb": row.verb}
    return document


def document(items: Items) -> dict:
    result = {"skipknowledge": True, "items": [row_json(row) for row in items.rows]}
    if items.rerun is not None:
        result["rerun"] = items.rerun
    return result


def render(items: Items) -> str:
    return json.dumps(document(items), ensure_ascii=False)
