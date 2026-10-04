from __future__ import annotations

from functools import singledispatch

from hoard.items import Head, Item, Items


def joined(title: str, subtitle: str) -> str:
    return f"{title} | {subtitle}" if subtitle else title


@singledispatch
def line(row) -> str:
    raise TypeError(f"cannot render {row!r}")


@line.register(Item)
def item_line(row: Item) -> str:
    return joined(row.title, row.subtitle)


@line.register(Head)
def head_line(row: Head) -> str:
    return "» " + joined(row.title, row.subtitle)


def render(items: Items) -> list:
    return [line(row) for row in items.rows]
