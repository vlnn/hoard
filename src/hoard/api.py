from __future__ import annotations

from typing import Callable, Optional

from hoard import _commands, _context, _db, _rows, _worker
from hoard.contract import Context, Kind
from hoard.items import Items


def context(kind: Kind, ctx: Optional[Context] = None) -> Context:
    ctx = ctx or _context.from_environ(kind)
    return ctx._replace(roots={storage.name: tuple(storage.roots(ctx)) for storage in kind.storages})


def open_database(kind: Kind, ctx: Context):
    return _db.connect(_db.path_for(kind.name, ctx.data))


def filter(kind: Kind, typed: str, ctx: Optional[Context] = None) -> Items:
    ctx = context(kind, ctx)
    con = open_database(kind, ctx)
    try:
        rows = _commands.rows_for(con, kind, ctx, typed)
        if not _worker.running(ctx):
            return Items(rows)
        return Items((_rows.updating(_commands.found_so_far(con)),) + rows, rerun=1)
    finally:
        con.close()


def update(
    kind: Kind,
    ctx: Optional[Context] = None,
    full: bool = False,
    on_progress: Optional[Callable[[int], None]] = None,
) -> int:
    from hoard import _index

    ctx = context(kind, ctx)
    con = open_database(kind, ctx)
    try:
        return _index.update(con, kind, ctx, on_progress or _index.ignore_progress, full)
    finally:
        con.close()


def act(kind: Kind, verb: str, ids, ctx: Optional[Context] = None) -> str:
    from hoard import _actions

    ctx = context(kind, ctx)
    con = open_database(kind, ctx)
    try:
        return _actions.dispatch(con, kind, ctx, verb, ids)
    finally:
        con.close()


def plan(kind: Kind, typed: str = "", ctx: Optional[Context] = None) -> list:
    ctx = context(kind, ctx)
    con = open_database(kind, ctx)
    try:
        return _commands.plan_for(con, kind, ctx, typed)
    finally:
        con.close()


def doctor(kind: Kind, ctx: Optional[Context] = None, settings=()):
    from hoard import _doctor

    return _doctor.checks(kind, context(kind, ctx), settings)
