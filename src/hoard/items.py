from __future__ import annotations

from typing import NamedTuple, Optional


class Item(NamedTuple):
    id: str
    title: str
    subtitle: str = ""
    icon: Optional[str] = None
    locator: Optional[str] = None
    verb: str = "open"


class Head(NamedTuple):
    name: str
    title: str
    subtitle: str = ""
    verb: Optional[str] = None


class Items(NamedTuple):
    rows: tuple = ()
    rerun: Optional[float] = None
