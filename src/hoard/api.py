from __future__ import annotations

from typing import Callable, Optional

from hoard import _commands, _context, _db, _progress, _rows, _standards, _worker
from hoard.contract import Context, Kind
from hoard.items import Items


def context(kind: Kind, ctx: Optional[Context] = None) -> Context:
    ctx = ctx or _context.from_environ(kind)
    return ctx._replace(roots={storage.name: tuple(storage.roots(ctx)) for storage in kind.storages})


def open_database(kind: Kind, ctx: Context):
    return _db.connect(_db.path_for(kind.name, ctx.data))


def opened(kind: Kind, ctx: Optional[Context]) -> tuple:
    ctx = context(kind, ctx)
    con = open_database(kind, ctx)
    return con, _standards.with_standards(con, ctx)


def filter(kind: Kind, typed: str, ctx: Optional[Context] = None) -> Items:
    con, ctx = opened(kind, ctx)
    try:
        rows = _commands.rows_for(con, kind, ctx, typed)
        if not _worker.running(ctx):
            return Items(rows)
        return Items((_rows.working(*_progress.current(con)),) + rows, rerun=1)
    finally:
        con.close()


def update(
    kind: Kind,
    ctx: Optional[Context] = None,
    full: bool = False,
    on_progress: Optional[Callable[[int], None]] = None,
) -> int:
    from hoard import _index

    con, ctx = opened(kind, ctx)
    try:
        found = _index.update(con, kind, ctx, on_progress or _index.ignore_progress, full)
        _standards.refresh(con, kind, ctx)
        return found
    finally:
        con.close()


def act(kind: Kind, verb: str, ids, ctx: Optional[Context] = None) -> str:
    from hoard import _actions

    con, ctx = opened(kind, ctx)
    try:
        return _actions.dispatch(con, kind, ctx, verb, ids)
    finally:
        con.close()


def plan(kind: Kind, typed: str = "", ctx: Optional[Context] = None) -> list:
    con, ctx = opened(kind, ctx)
    try:
        return _commands.plan_for(con, kind, ctx, typed)
    finally:
        con.close()


def ask(kind: Kind, ctx: Optional[Context] = None, questions: Optional[list] = None) -> int:
    from hoard import _ask

    con, ctx = opened(kind, ctx)
    try:
        return _ask.run(con, kind, ctx, questions)
    finally:
        con.close()


def embed(kind: Kind, ctx: Optional[Context] = None) -> int:
    from hoard import _embed

    con, ctx = opened(kind, ctx)
    try:
        return _embed.run(con, kind, ctx)
    finally:
        con.close()


def ask_dry_run(kind: Kind, ctx: Optional[Context] = None, questions: Optional[list] = None) -> list:
    from hoard import _ask

    con, ctx = opened(kind, ctx)
    try:
        return _ask.dry_run(con, kind, ctx, questions)
    finally:
        con.close()


def __getattr__(name: str):
    if name == "ModelError":
        from hoard._http import ModelError

        return ModelError
    raise AttributeError(f"module 'hoard.api' has no attribute {name!r}")


def doctor(kind: Kind, ctx: Optional[Context] = None, settings=()):
    from hoard import _doctor

    return _doctor.checks(kind, context(kind, ctx), settings)
