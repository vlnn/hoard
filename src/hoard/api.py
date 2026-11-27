from __future__ import annotations

from typing import Callable, Optional

from hoard import _asleep, _commands, _context, _db, _progress, _rows, _search, _standards, _worker
from hoard.contract import NOTHING, Context, Kind
from hoard.items import Items


def settings(kind: Kind, ctx: Optional[Context]) -> Context:
    return ctx or _context.from_environ(kind)


def context(kind: Kind, ctx: Optional[Context] = None) -> Context:
    ctx = settings(kind, ctx)
    return ctx._replace(roots={storage.name: tuple(storage.roots(ctx)) for storage in kind.storages}, asleep=NOTHING)


def open_database(kind: Kind, ctx: Context):
    return _db.connect(_db.path_for(kind.name, ctx.data))


def opened(kind: Kind, ctx: Optional[Context]) -> tuple:
    ctx = context(kind, ctx)
    con = open_database(kind, ctx)
    return con, _standards.with_standards(con, ctx)


def opened_for_a_keystroke(kind: Kind, ctx: Optional[Context]) -> tuple:
    ctx = settings(kind, ctx)
    con = open_database(kind, ctx)
    return con, _standards.with_standards(con, _asleep.context(con, kind, ctx))


def filter(kind: Kind, typed: str, ctx: Optional[Context] = None, module: Optional[str] = None) -> Items:
    con, ctx = opened_for_a_keystroke(kind, ctx)
    try:
        rows = _commands.rows_for(con, kind, ctx, typed)
        if not _search.is_empty(con) and _worker.refresh_if_stale(module, con, ctx):
            return Items((_rows.starting(),) + rows, rerun=1)
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


def reopen_alfred(query: str) -> None:
    from hoard import _requery

    _requery.reopen(query)


def act(
    kind: Kind,
    verb: str,
    ids,
    ctx: Optional[Context] = None,
    follow_up: Optional[Callable[[str], None]] = None,
) -> str:
    from hoard import _actions

    con, ctx = opened(kind, ctx)
    try:
        reply = _actions.dispatch(con, kind, ctx, verb, ids)
    finally:
        con.close()
    if reply.then:
        (follow_up or reopen_alfred)(reply.then)
    return reply.message


def plan(kind: Kind, typed: str = "", ctx: Optional[Context] = None) -> list:
    con, ctx = opened(kind, ctx)
    try:
        return _commands.plan_for(con, kind, ctx, typed)
    finally:
        con.close()


def carry_out(kind: Kind, steps, ctx: Context) -> list:
    from hoard import _steps

    return _steps.carry_out(steps, kind, ctx)


def restore(kind: Kind, changes, ctx: Context) -> None:
    from hoard import _steps

    _steps.undo_changes(changes, kind, ctx)


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
        from hoard.alfred.chat import ModelError

        return ModelError
    raise AttributeError(f"module 'hoard.api' has no attribute {name!r}")


def doctor(kind: Kind, ctx: Optional[Context] = None, settings=()):
    from hoard import _doctor

    return _doctor.checks(kind, context(kind, ctx), settings)
