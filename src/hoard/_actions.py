from __future__ import annotations

import sqlite3

from hoard import _commands, _fold, _index, _journal, _models, _plan, _rows, _search, _system
from hoard.contract import Context, Kind, Verb

BATCH = "batch:"
HEAD = "head:"
PLAN = "plan:"


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


def outcome(kind: Kind, verb: Verb, titles: list) -> str:
    if not titles:
        return f"{verb.label}: nothing to do"
    named = titles[0] if len(titles) == 1 else _rows.counted(kind, len(titles))
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
    return outcome(kind, verb, changed_titles(rows, changes))


def undoer(kind: Kind, verb_name: str):
    if verb_name == "apply":
        return "Fix", _plan.undo_changes
    verb = kind.verbs.get(verb_name)
    return (verb.label, verb.undo) if verb and verb.undo else None


def undo_last(con: sqlite3.Connection, kind: Kind, ctx: Context) -> str:
    batch = _journal.last_undoable(con)
    found = undoer(kind, batch.verb) if batch else None
    if found is None:
        return "Nothing to undo"
    label, undo = found
    undo(batch.changes, ctx)
    _journal.forget(con, batch.number)
    con.commit()
    _index.update(con, kind, ctx)
    return f"Undid {label}"


def steps_from(con: sqlite3.Connection, kind: Kind, ctx: Context, ids) -> list:
    steps = []
    for given in ids:
        if given.startswith(_plan.PREFIX):
            steps.append(_plan.decode(given))
        elif given.startswith(PLAN):
            steps += _commands.plan_for(con, kind, ctx, given[len(PLAN) :])
    return steps


def fixed(changes: list, skipped: int) -> str:
    if not changes:
        message = "Nothing fixed"
    elif len(changes) == 1:
        message = f"Fixed {_plan.name_of(changes[0])}"
    else:
        message = f"Fixed {len(changes)} items"
    return message + (f" · {skipped} skipped" if skipped else "")


def apply_plan(con: sqlite3.Connection, kind: Kind, ctx: Context, ids) -> str:
    steps = steps_from(con, kind, ctx, ids)
    changes = [change for change in (_plan.apply_step(step, ctx) for step in steps) if change]
    if changes:
        _journal.record(con, "apply", changes, undoable=True)
        con.commit()
        _index.update(con, kind, ctx)
    return fixed(changes, len(steps) - len(changes))


def use_model(con: sqlite3.Connection, ids) -> str:
    _, role, model = ids[0].split(":", 2)
    _models.use(con, role, model)
    con.commit()
    return f"{role.title()} model: {model}"


def dispatch(con: sqlite3.Connection, kind: Kind, ctx: Context, verb: str, ids) -> str:
    if verb in _system.SYSTEM_VERBS:
        return _system.hand_over(kind, resolve(con, kind, ctx, ids), verb)
    if verb == "undo":
        return undo_last(con, kind, ctx)
    if verb == "apply":
        return apply_plan(con, kind, ctx, ids)
    if verb == "use_model":
        return use_model(con, ids)
    if verb in kind.verbs:
        return run_kind_verb(con, kind, ctx, verb, ids)
    return f"No verb {verb}"
