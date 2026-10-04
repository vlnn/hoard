from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Item:
    id: str
    title: str
    subtitle: str = ""
    icon: Optional[str] = None
    locator: Optional[str] = None
    verb: str = "open"


@dataclass(frozen=True)
class Head:
    name: str
    title: str
    subtitle: str = ""
    verb: Optional[str] = None


@dataclass(frozen=True)
class Items:
    rows: tuple = ()
    rerun: Optional[float] = None
