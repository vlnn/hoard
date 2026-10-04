from __future__ import annotations

import sqlite3

from hoard import _commands, _fold, _index, _journal, _search, _system
from hoard.contract import Context, Kind, Verb

BATCH = "batch:"
HEAD = "head:"


def expanded(con: sqlite3.Connection, kind: Kind, ctx: Context, ids) -> list:
    found = []
    for given in ids:
        if given.startswith(BATCH):
            found += _commands.batch_ids(con, kind, ctx, given[len(BATCH) :])
        elif not given.startswith(HEAD):
            found.append(given)
    return found


def resolve(con: sqlite3.Connection, kind: Kind, ctx: Context, ids) -> list:
    return _fold.fold(con, kind, ctx, _search.by_ids(con, expanded(con, kind, ctx, ids)))


def outcome(verb: Verb, titles: list) -> str:
    if not titles:
        return f"{verb.label}: nothing to do"
    named = titles[0] if len(titles) == 1 else f"{len(titles)} items"
    return f"{verb.label}: {named}" + ("" if verb.undoable else " (cannot be undone)")


def changed_titles(rows: list, changes) -> list:
    changed = {change.id for change in changes}
    return [row.found.entity.title for row in rows if row.found.entity.id in changed]


def run_kind_verb(con: sqlite3.Connection, kind: Kind, ctx: Context, name: str, ids) -> str:
    verb, rows = kind.verbs[name], resolve(con, kind, ctx, ids)
    changes = tuple(verb.run([row.found for row in rows], ctx))
    if changes:
        _journal.record(con, name, changes, verb.undoable)
        con.commit()
        _index.update(con, kind, ctx)
    return outcome(verb, changed_titles(rows, changes))


def undo_last(con: sqlite3.Connection, kind: Kind, ctx: Context) -> str:
    batch = _journal.last_undoable(con)
    verb = kind.verbs.get(batch.verb) if batch else None
    if verb is None or verb.undo is None:
        return "Nothing to undo"
    verb.undo(batch.changes, ctx)
    _journal.forget(con, batch.number)
    con.commit()
    _index.update(con, kind, ctx)
    return f"Undid {verb.label}"


def dispatch(con: sqlite3.Connection, kind: Kind, ctx: Context, verb: str, ids) -> str:
    if verb in _system.SYSTEM_VERBS:
        return _system.hand_over(resolve(con, kind, ctx, ids), verb)
    if verb == "undo":
        return undo_last(con, kind, ctx)
    if verb in kind.verbs:
        return run_kind_verb(con, kind, ctx, verb, ids)
    return f"No verb {verb}"
