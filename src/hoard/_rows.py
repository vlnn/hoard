from __future__ import annotations

import json

from hoard.contract import Entity, Kind
from hoard.items import Head, Item


def subtitle(fields) -> str:
    return " · ".join(value for value in fields if value)


def entity_item(kind: Kind, row: tuple) -> Item:
    entity_id, title, fields_json, icon, locator = row
    fields = tuple(json.loads(fields_json))
    verb = kind.default_verb(Entity(entity_id, title, fields))
    return Item(entity_id, title, subtitle(fields), icon, locator, verb)


def index_empty() -> Head:
    return Head("update", "Index is empty", "↩ to update the index", verb="update")


def update_offer() -> Head:
    return Head("update", "Update the index", "↩ to read every storage again", verb="update")


def no_match(typed: str) -> Head:
    return Head("none", f"No match for {typed.strip()}")


def updating(found: int) -> Head:
    return Head("updating", "Updating the index…", f"{found} found so far")
