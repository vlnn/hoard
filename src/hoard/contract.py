from __future__ import annotations

import importlib
import os
from types import MappingProxyType
from typing import Any, Callable, Mapping, NamedTuple, Optional, Sequence

NOTHING = MappingProxyType({})


class ContractError(ValueError):
    pass


class Entity(NamedTuple):
    id: str
    title: str
    fields: tuple = ()
    text: str = ""
    cover: bytes = b""


class Sighting(NamedTuple):
    id: str
    storage: str
    locator: Optional[str]
    mtime: float
    size: int


class Context(NamedTuple):
    data: str
    cache: str
    config: Mapping[str, str] = NOTHING
    journal: Optional[Callable[..., Any]] = None

    def setting(self, name: str, default: str = "") -> str:
        return self.config.get(name, default)


class Storage(NamedTuple):
    name: str
    roots: Callable[[Context], Sequence[str]]
    reader: Callable[[str], Optional[Entity]]
    mounted: Callable[[str], bool] = os.path.isdir


class Change(NamedTuple):
    id: str
    kind_of_change: str
    before: Any
    after: Any


class Verb(NamedTuple):
    label: str
    run: Callable[[Sequence[str], Context], Sequence[Change]]
    undo: Optional[Callable[[Sequence[Change], Context], None]] = None

    @property
    def undoable(self) -> bool:
        return self.undo is not None


class Command(NamedTuple):
    label: str
    rows: Callable[[Sequence[str], Context], Sequence[Any]]
    verb: str
    heads: Optional[Callable[[Sequence[str], Context], Sequence[Any]]] = None


class Step(NamedTuple):
    verb: str
    id: str
    before: Any
    after: Any
    reason: str


class Plan(NamedTuple):
    steps: tuple = ()


def no_icon(entity: Entity) -> Optional[str]:
    return None


def always_open(entity: Entity) -> str:
    return "open"


class _KindRecord(NamedTuple):
    name: str
    keyword: str
    storages: tuple
    fields: tuple
    evidence: Callable[[Entity], str]
    icon: Callable[[Entity], Optional[str]] = no_icon
    default_verb: Callable[[Entity], str] = always_open
    verbs: Mapping[str, Verb] = NOTHING
    commands: Mapping[str, Command] = NOTHING
    labels: Mapping[str, str] = NOTHING


class Kind(_KindRecord):
    __slots__ = ()

    def __new__(cls, *args: Any, **kwargs: Any) -> "Kind":
        kind = super().__new__(cls, *args, **kwargs)
        for problem in problems(kind):
            raise ContractError(f"{kind.name or 'kind'}: {problem}")
        return kind


def problems(kind: Kind) -> list:
    checks = (
        (kind.name.isidentifier() and kind.name.islower(), "name should be a lowercase identifier"),
        (bool(kind.keyword) and isinstance(kind.keyword, str), "keyword should be a non-empty string"),
        (isinstance(kind.storages, tuple), "storages should be a tuple, in display order"),
        (all(isinstance(s, Storage) for s in kind.storages), "storages should be Storage records"),
        (len({s.name for s in kind.storages}) == len(kind.storages), "storage names should be unique"),
        (isinstance(kind.fields, tuple), "fields should be a tuple, in display order"),
        (all(isinstance(f, str) for f in kind.fields), "field labels should be strings"),
        (callable(kind.evidence), "evidence should be callable"),
        (callable(kind.icon), "icon should be callable"),
        (callable(kind.default_verb), "default_verb should be callable"),
        (all(isinstance(v, Verb) for v in kind.verbs.values()), "verbs should be Verb records"),
        (all(isinstance(c, Command) for c in kind.commands.values()), "commands should be Command records"),
    )
    return [message for passed, message in checks if not passed]


class roots_from(NamedTuple):
    setting: str

    def __call__(self, ctx: Context) -> list:
        return [line.strip() for line in ctx.setting(self.setting).splitlines() if line.strip()]


class lazy(NamedTuple):
    module: str
    name: str

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return getattr(importlib.import_module(self.module), self.name)(*args, **kwargs)

    def __repr__(self) -> str:
        return f"lazy({self.module}:{self.name})"
