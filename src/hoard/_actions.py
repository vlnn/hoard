from __future__ import annotations

import json
import sqlite3

from hoard import (
    _commands,
    _fold,
    _index,
    _journal,
    _models,
    _names,
    _plan,
    _requery,
    _rows,
    _search,
    _suggest,
    _system,
    _tags,
)
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


def plan_undo(con, changes, ctx) -> None:
    _plan.undo_changes(changes, ctx)


KERNEL_UNDO = {"apply": plan_undo, "accept": _names.undo, "set_tag": _tags.undo, "accept_tags": _tags.undo}


def kind_undo(verb):
    return lambda con, changes, ctx: verb.undo(changes, ctx)


def undoer(kind: Kind, verb_name: str):
    if verb_name in KERNEL_UNDO:
        return _commands.KERNEL_LABELS[verb_name], KERNEL_UNDO[verb_name]
    verb = kind.verbs.get(verb_name)
    return (verb.label, kind_undo(verb)) if verb and verb.undo else None


def undo_last(con: sqlite3.Connection, kind: Kind, ctx: Context) -> str:
    batch = _journal.last_undoable(con)
    found = undoer(kind, batch.verb) if batch else None
    if found is None:
        return "Nothing to undo"
    label, undo = found
    undo(con, batch.changes, ctx)
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


def record(con: sqlite3.Connection, verb: str, changes: list) -> None:
    if changes:
        _journal.record(con, verb, changes, undoable=True)
    con.commit()


def title_of(con: sqlite3.Connection, entity_id: str) -> str:
    return con.execute("SELECT title FROM entities WHERE id = ?", (entity_id,)).fetchone()[0]


def names_for(con, kind: Kind, ids) -> list:
    if ids and ids[0].startswith("names:"):
        return _names.pending(con, kind, ids[0][len("names:") :])
    wanted = set(ids)
    return [suggestion for suggestion in _names.pending(con, kind) if suggestion.id in wanted]


def accept_names(con, kind: Kind, ctx: Context, ids) -> str:
    changes = _names.accept(con, kind, names_for(con, kind, ids))
    record(con, "accept", changes)
    return f"Accepted {_commands.plural(len(changes), 'name')}"


def tagged(con, kind: Kind, changes: list, tag: str = "") -> str:
    if not changes:
        return "Nothing tagged"
    who = title_of(con, changes[0].id) if len(changes) == 1 else _rows.counted(kind, len(changes))
    return f"Tagged {who}" + (f": {tag}" if tag else "")


def targets_of(con, target: str) -> list:
    if target.startswith(_suggest.EVERY):
        return _suggest.untagged_ids(con, _suggest.target_words(target))
    return [target[1:]]


def set_tags(con, kind: Kind, ctx: Context, ids) -> str:
    target, tag = json.loads(ids[0][len(_suggest.CHOICE) :])
    changes = [_tags.set_tag(con, entity_id, tag, "hand") for entity_id in targets_of(con, target)]
    record(con, "set_tag", changes)
    return tagged(con, kind, changes, tag)


def accept_tags(con, kind: Kind, ctx: Context, ids) -> str:
    typed = ids[0][len("suggested:") :] if ids else ""
    changes = [_tags.set_tag(con, i, _tags.suggestion(con, i), "model") for i in _suggest.suggested_ids(con, typed)]
    record(con, "accept_tags", changes)
    tags = {change.after[0][0] for change in changes}
    return tagged(con, kind, changes, tags.pop() if len(tags) == 1 and len(changes) == 1 else "")


def like(kind: Kind, ids) -> str:
    _requery.reopen(f"{kind.keyword} like #{ids[0]}")
    return ""


def pick(kind: Kind, ids) -> str:
    given = ids[0] if ids else ""
    target = given[len("pick:") :] if given.startswith("pick:") else f"#{given}"
    _requery.reopen(f"{kind.keyword} tag {target} ")
    return ""


def dispatch(con: sqlite3.Connection, kind: Kind, ctx: Context, verb: str, ids) -> str:
    if verb in _system.SYSTEM_VERBS:
        return _system.hand_over(kind, resolve(con, kind, ctx, ids), verb)
    if verb == "undo":
        return undo_last(con, kind, ctx)
    if verb == "apply":
        return apply_plan(con, kind, ctx, ids)
    if verb == "use_model":
        return use_model(con, ids)
    if verb == "accept":
        return accept_names(con, kind, ctx, ids)
    if verb == "set_tag":
        return set_tags(con, kind, ctx, ids)
    if verb == "accept_tags":
        return accept_tags(con, kind, ctx, ids)
    if verb == "pick":
        return pick(kind, ids)
    if verb == "like" and ids:
        return like(kind, ids)
    if verb in kind.verbs:
        return run_kind_verb(con, kind, ctx, verb, ids)
    return f"No verb {verb}"
