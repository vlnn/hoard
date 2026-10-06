from __future__ import annotations

from typing import NamedTuple, Optional


class Mod(NamedTuple):
    key: str
    verb: str
    subtitle: str


class Item(NamedTuple):
    id: str
    title: str
    subtitle: str = ""
    icon: Optional[str] = None
    locator: Optional[str] = None
    verb: str = "open"
    mods: tuple = ()


class Head(NamedTuple):
    name: str
    title: str
    subtitle: str = ""
    verb: Optional[str] = None
    arg: str = ""
    complete: str = ""


class Items(NamedTuple):
    rows: tuple = ()
    rerun: Optional[float] = None
