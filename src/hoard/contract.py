from __future__ import annotations

import importlib
import os
from types import MappingProxyType
from typing import Any, Callable, Mapping, NamedTuple, Optional, Sequence

NOTHING = MappingProxyType({})
KERNEL_VERBS = frozenset(
    {"open", "reveal", "update", "undo", "apply", "use_model", "ask", "accept", "pick", "set_tag", "accept_tags", "like", "embed"}
)
KERNEL_COMMANDS = frozenset({"update", "undo", "rnd", "stats", "fix", "model", "name", "tag", "like"})
STEP_VERBS = frozenset({"move", "trash"})
COMMAND_VERBS = frozenset({"open", "reveal"})
LABELS = frozenset({"one", "many"})


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
    reachable: bool = True


class Found(NamedTuple):
    entity: Entity
    sightings: tuple

    @property
    def storages(self) -> tuple:
        return tuple(sighting.storage for sighting in self.sightings)

    @property
    def nearest(self) -> Optional[Sighting]:
        return next((s for s in self.sightings if s.reachable), self.sightings[0] if self.sightings else None)

    def on(self, storage: str) -> bool:
        return storage in self.storages

    def locator_in(self, storage: str) -> Optional[str]:
        return next((s.locator for s in self.sightings if s.storage == storage), None)


class Context(NamedTuple):
    data: str
    cache: str
    config: Mapping[str, str] = NOTHING
    journal: Optional[Callable[..., Any]] = None
    roots: Mapping[str, tuple] = NOTHING

    def setting(self, name: str, default: str = "") -> str:
        return self.config.get(name, default)

    def roots_of(self, storage: str) -> tuple:
        return tuple(self.roots.get(storage, ()))


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
    run: Callable[[Sequence[Found], Context], Sequence[Change]]
    undo: Optional[Callable[[Sequence[Change], Context], None]] = None

    @property
    def undoable(self) -> bool:
        return self.undo is not None


def everything(found: Found) -> bool:
    return True


class Command(NamedTuple):
    label: str
    verb: str
    keep: Callable[[Found], bool] = everything
    on: tuple = ()
    off: tuple = ()


class Step(NamedTuple):
    verb: str
    id: str
    before: Any
    after: Any
    reason: str


class Plan(NamedTuple):
    steps: tuple = ()


class TextEmbedding(NamedTuple):
    trim: int = 1500

    def text(self, evidence: str) -> str:
        return evidence[: self.trim]


def no_icon(entity: Entity) -> Optional[str]:
    return None


def always_open(found: Found) -> str:
    return "open"


class _KindRecord(NamedTuple):
    name: str
    keyword: str
    storages: tuple
    fields: tuple
    evidence: Callable[[Entity], str]
    icon: Callable[[Entity], Optional[str]] = no_icon
    default_verb: Callable[[Found], str] = always_open
    verbs: Mapping[str, Verb] = NOTHING
    commands: Mapping[str, Command] = NOTHING
    labels: Mapping[str, str] = NOTHING
    lint: Optional[Callable[[Sequence[Found], Context], Plan]] = None
    derive: Mapping[str, Callable[[Found], Optional[str]]] = NOTHING
    nameable: tuple = ()
    tags: Optional[Callable[[Context], Sequence[str]]] = None
    like: Optional[TextEmbedding] = TextEmbedding()
    last_opened: Optional[Callable[[Context], Optional[str]]] = None


class Kind(_KindRecord):
    __slots__ = ()

    def __new__(cls, *args: Any, **kwargs: Any) -> "Kind":
        kind = super().__new__(cls, *args, **kwargs)
        for problem in problems(kind):
            raise ContractError(f"{kind.name or 'kind'}: {problem}")
        return kind


def storage_names(kind: Kind) -> set:
    return {storage.name for storage in kind.storages if isinstance(storage, Storage)}


def commands(kind: Kind) -> list:
    return [c for c in kind.commands.values() if isinstance(c, Command)]


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
        (kind.lint is None or callable(kind.lint), "lint should be callable or None"),
        (all(isinstance(v, Verb) for v in kind.verbs.values()), "verbs should be Verb records"),
        (all(isinstance(c, Command) for c in kind.commands.values()), "commands should be Command records"),
        (not KERNEL_VERBS & set(kind.verbs), f"verb names {sorted(KERNEL_VERBS)} belong to the kernel"),
        (not KERNEL_COMMANDS & set(kind.commands), f"command words {sorted(KERNEL_COMMANDS)} belong to the kernel"),
        (all(w.isalpha() and w.islower() for w in kind.commands), "command words should be single lowercase words"),
        (all(c.verb in COMMAND_VERBS or c.verb in kind.verbs for c in commands(kind)), "commands should name a known verb"),
        (all(set(c.on) | set(c.off) <= storage_names(kind) for c in commands(kind)), "on and off should name storages"),
        (set(kind.labels) <= LABELS, f"labels should be among {sorted(LABELS)}"),
        (all(key.isidentifier() and key.islower() for key in kind.derive), "derived keys should be lowercase identifiers"),
        (all(callable(producer) for producer in kind.derive.values()), "derived producers should be callable"),
        (set(kind.nameable) <= set(kind.fields), "nameable should name the kind's fields"),
        (kind.tags is None or callable(kind.tags), "tags should be callable with the context, or None"),
        (kind.like is None or isinstance(kind.like, TextEmbedding), "like should be a TextEmbedding or None"),
        (kind.last_opened is None or callable(kind.last_opened), "last_opened should be callable or None"),
        (all(isinstance(value, str) for value in kind.labels.values()), "labels should be strings"),
    )
    return [message for passed, message in checks if not passed]


class roots_from(NamedTuple):
    setting: str

    def __call__(self, ctx: Context) -> list:
        return [line.strip() for line in ctx.setting(self.setting).splitlines() if line.strip()]


class lines_from(NamedTuple):
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
