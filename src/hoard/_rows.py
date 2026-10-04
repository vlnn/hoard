from __future__ import annotations

from typing import Optional

from hoard._fold import Row
from hoard.contract import Context, Found, Kind
from hoard.items import Head, Item, Mod

SYSTEM_MODS = (Mod("shift", "open", "Open"), Mod("alt", "reveal", "Reveal in Finder"))
TAG_MOD = Mod("cmd", "pick", "Tag…")


def mods_for(kind: Kind, reachable: bool) -> tuple:
    found = SYSTEM_MODS if reachable else ()
    return found + ((TAG_MOD,) if kind.tags else ())


def counted(kind: Kind, count: int) -> str:
    noun = kind.labels.get("one", "item") if count == 1 else kind.labels.get("many", "items")
    return f"{count} {noun}"


def places(found: Found) -> str:
    nearest = found.nearest
    if nearest is None:
        return ""
    others = "".join(f" +{storage}" for storage in found.storages if storage != nearest.storage)
    return nearest.storage + others + ("" if nearest.reachable else " (not reachable)")


def subtitle(kind: Kind, found: Found) -> str:
    parts = [places(found)] if len(kind.storages) > 1 else []
    parts += [value for value in found.entity.fields if value]
    return " · ".join(part for part in parts if part)


def entity_item(kind: Kind, row: Row, verb: Optional[str] = None) -> Item:
    found, nearest = row.found, row.found.nearest
    reachable = nearest is not None and nearest.reachable
    return Item(
        id=found.entity.id,
        title=found.entity.title,
        subtitle=subtitle(kind, found),
        icon=row.icon,
        locator=nearest.locator if nearest else None,
        verb=verb or kind.default_verb(found),
        mods=mods_for(kind, reachable),
    )


def missing_folders(kind: Kind, ctx: Context) -> tuple:
    heads = []
    for storage in kind.storages:
        roots = ctx.roots_of(storage.name)
        if not roots:
            setting = getattr(storage.roots, "setting", "its folder")
            heads.append(Head(f"setup:{storage.name}", f"No folder set for {storage.name}", f"set {setting} in the workflow configuration"))
        heads += [
            Head(f"unreachable:{storage.name}", f"Not reachable: {root}", f"{storage.name} · is the drive connected?")
            for root in roots
            if not storage.mounted(root)
        ]
    return tuple(heads)


def index_empty() -> Head:
    return Head("update", "Index is empty", "↩ to update the index", verb="update")


def empty_index_rows(kind: Kind, ctx: Context) -> tuple:
    return missing_folders(kind, ctx) + (index_empty(),)


def update_offer() -> Head:
    return Head("update", "Update the index", "↩ to read every storage again", verb="update")


def no_match(typed: str) -> Head:
    return Head("none", f"No match for {typed.strip()}")


def updating(found: int) -> Head:
    return Head("updating", "Updating the index…", f"{found} found so far")
