from __future__ import annotations

import sqlite3
import time

import hoard
from hoard import _db, _fold, _journal, _models, _plan, _rows, _search
from hoard.contract import Command, Context, Kind, everything
from hoard.items import Head, Item

RANDOM_ROWS = 10


def ago(seconds_since) -> str:
    if seconds_since is None:
        return "never"
    elapsed = max(0, time.time() - seconds_since)
    for size, unit in ((86400, "days"), (3600, "h"), (60, "min")):
        if elapsed >= size:
            return f"{int(elapsed // size)} {unit} ago"
    return "just now"


def plural(count: int, one: str, many: str = "") -> str:
    return f"{count} {one}" if count == 1 else f"{count} {many or one + 's'}"


def items_for(con: sqlite3.Connection, kind: Kind, ctx: Context, entity_rows: list) -> tuple:
    return tuple(_rows.entity_item(kind, row, ctx=ctx) for row in _fold.fold(con, kind, ctx, entity_rows))


def update_rows(con, kind, ctx, words) -> tuple:
    return (_rows.update_offer(),)


KERNEL_LABELS = {
    "apply": "Fix",
    "accept": "Accept names",
    "set_tag": "Tag",
    "accept_tags": "Accept tags",
    "standardize": "Standardize",
    "keep_apart": "Keep apart",
}


def verb_label(kind: Kind, verb: str) -> str:
    return kind.verbs[verb].label if verb in kind.verbs else KERNEL_LABELS.get(verb, verb)


def undo_rows(con, kind, ctx, words) -> tuple:
    batch = _journal.last_undoable(con)
    if batch is None:
        return (Head("none", "Nothing to undo"),)
    detail = f"{plural(len(batch.changes), 'change')} · {ago(batch.at)}"
    return (Head("undo", f"Undo {verb_label(kind, batch.verb)}", detail, verb="undo"),)


def rnd_rows(con, kind, ctx, words) -> tuple:
    return items_for(con, kind, ctx, _search.random_entities(con, RANDOM_ROWS))


def storage_head(con: sqlite3.Connection, name: str, mounted: tuple) -> Head:
    (count,) = con.execute("SELECT count(*) FROM sightings WHERE storage = ?", (name,)).fetchone()
    row = con.execute("SELECT last_update_at FROM storage_state WHERE storage = ?", (name,)).fetchone()
    reach = "reachable" if mounted else "not reachable"
    return Head(f"stats:{name}", f"{name}: {count}", f"{reach} · updated {ago(row[0] if row else None)}")


def stats_rows(con, kind, ctx, words) -> tuple:
    (entities,) = con.execute("SELECT count(*) FROM entities").fetchone()
    mounted = _fold.mounted_roots(kind, ctx)
    return (
        Head("stats", _rows.counted(kind, entities)),
        *(storage_head(con, s.name, mounted[s.name]) for s in kind.storages),
        Head("stats:hoard", f"hoard {hoard.__version__}", f"schema v{_db.schema_version(con)}"),
    )


def plan_for(con, kind: Kind, ctx: Context, typed: str) -> list:
    if kind.lint is None:
        return []
    rows = _fold.fold(con, kind, ctx, _search.search(con, typed, _search.EVERYTHING, order=_search.order_of(kind)))
    steps = list(kind.lint([row.found for row in rows], ctx).steps)
    return [step for step in steps if step.id] if typed.strip() else steps


def step_item(step) -> Item:
    return Item(_plan.encode(step), _plan.step_title(step), _plan.step_subtitle(step), locator=step.before, verb="apply")


def fix_rows(con, kind, ctx, words) -> tuple:
    typed = " ".join(words)
    steps = plan_for(con, kind, ctx, typed)
    if not steps:
        return (Head("none", "Nothing to fix"),)
    head = Head("plan", f"Apply {len(steps)}", "↩ runs every step below", verb="apply", arg=f"plan:{typed.lower()}")
    return (head,) + tuple(step_item(step) for step in steps[: _search.LIMIT])


KERNEL_COMMANDS = {"update": update_rows, "undo": undo_rows, "rnd": rnd_rows, "stats": stats_rows, "fix": fix_rows}


def final(kind: Kind, verb: str) -> bool:
    return verb in kind.verbs and not kind.verbs[verb].undoable


def in_sql_only(command: Command) -> bool:
    return command.keep is everything


def batch_head(kind: Kind, batch: str, command: Command, total: int) -> Head:
    subtitle = "↩ on every row below" + (" · cannot be undone" if final(kind, command.verb) else "")
    return Head("batch", f"{command.label} all {total}", subtitle, verb=command.verb, arg=f"batch:{batch}")


def kept_rows(con, kind: Kind, ctx: Context, command: Command, typed: str) -> list:
    every = _search.search(con, typed, _search.EVERYTHING, command.on, command.off, order=_search.order_of(kind))
    return [row for row in _fold.fold(con, kind, ctx, every) if command.keep(row.found)]


def shown_and_total(con, kind: Kind, ctx: Context, command: Command, typed: str) -> tuple:
    if in_sql_only(command):
        found = _search.search(con, typed, _search.LIMIT, command.on, command.off, order=_search.order_of(kind))
        shown = _fold.fold(con, kind, ctx, found)
        return shown, _search.count(con, typed, command.on, command.off)
    kept = kept_rows(con, kind, ctx, command, typed)
    return kept[: _search.LIMIT], len(kept)


def command_rows(con, kind: Kind, ctx: Context, word: str, words: list) -> tuple:
    command, typed = kind.commands[word], " ".join(words)
    shown, total = shown_and_total(con, kind, ctx, command, typed)
    if not total:
        return (Head("none", f"Nothing to {command.label.lower()}"),)
    head = batch_head(kind, " ".join([word, *words]).lower(), command, total)
    return (head,) + tuple(_rows.entity_item(kind, row, command.verb, ctx) for row in shown)


def batch_ids(con, kind: Kind, ctx: Context, batch: str) -> list:
    word, words = _search.split_command(batch)
    command, typed = kind.commands.get(word), " ".join(words)
    if command is None:
        return []
    if in_sql_only(command):
        return _search.ids(con, typed, command.on, command.off, order=_search.order_of(kind))
    return [row.found.entity.id for row in kept_rows(con, kind, ctx, command, typed)]


def search_rows(con, kind: Kind, ctx: Context, typed: str) -> tuple:
    found = items_for(con, kind, ctx, _search.search(con, typed, order=_search.order_of(kind)))
    return found or (_rows.no_match(typed),)


def model_item(role: str, model: str, chosen: str) -> Item:
    state = "in use" if model == chosen else "↩ to use"
    return Item(f"model:{role}:{model}", model, f"{role} · {state}", verb="use_model")


def role_rows(con, ctx: Context, role: str) -> list:
    from hoard._http import ModelError

    url = _models.url_of(ctx, role)
    try:
        offered = _models.available(url, _models.key_of(ctx, role))
    except ModelError as error:
        return [Head(f"model:{role}", f"{role.title()} server not reachable", f"{url} · {error.reason}")]
    chosen = _models.model_of(con, role)
    return [Head(f"model:{role}", f"{role.title()} models", url)] + [model_item(role, m, chosen) for m in offered]


def model_rows(con, kind, ctx, words) -> tuple:
    return tuple(row for role in _models.configured(ctx) for row in role_rows(con, ctx, role))


def name_rows(con, kind, ctx, words) -> tuple:
    from hoard import _suggest

    return _suggest.name_rows(con, kind, ctx, words)


def tag_rows(con, kind, ctx, words) -> tuple:
    from hoard import _suggest

    return _suggest.tag_rows(con, kind, ctx, words)


def std_rows(con, kind, ctx, words) -> tuple:
    from hoard import _suggest

    return _suggest.std_rows(con, kind, ctx, words)


def like_rows(con, kind, ctx, words) -> tuple:
    from hoard import _like

    return _like.like_rows(con, kind, ctx, words)


def always(con, kind, ctx) -> bool:
    return True


def models_configured(con, kind, ctx) -> bool:
    return bool(_models.configured(ctx))


def nameable(con, kind, ctx) -> bool:
    return bool(kind.nameable) and "chat" in _models.configured(ctx) and not _search.is_empty(con)


def taggable(con, kind, ctx) -> bool:
    return bool(kind.tags) and bool(kind.tags(ctx)) and not _search.is_empty(con)


def standardizable(con, kind, ctx) -> bool:
    return bool(kind.standards) and not _search.is_empty(con)


def likeable(con, kind, ctx) -> bool:
    return _rows.likeable(kind, ctx) and not _search.is_empty(con)


OPTIONAL_COMMANDS = {
    "update": (always, update_rows),
    "model": (models_configured, model_rows),
    "name": (nameable, name_rows),
    "tag": (taggable, tag_rows),
    "like": (likeable, like_rows),
    "std": (standardizable, std_rows),
}

MIN_COMPLETION = 2
COMPLETES = "↩ to complete"


def offers_optional(con, kind: Kind, ctx: Context, word: str) -> bool:
    offered, _ = OPTIONAL_COMMANDS.get(word, (None, None))
    return offered is not None and offered(con, kind, ctx)


def offers(con, kind: Kind, ctx: Context, word: str) -> bool:
    return word in KERNEL_COMMANDS or word in kind.commands or offers_optional(con, kind, ctx, word)


def command_words(kind: Kind) -> list:
    return sorted({*OPTIONAL_COMMANDS, *KERNEL_COMMANDS, *kind.commands})


def partial_word(typed: str) -> str:
    return typed.lower() if len(typed) >= MIN_COMPLETION and typed.split() == [typed] else ""


def completion_head(kind: Kind, word: str) -> Head:
    return Head(f"complete:{word}", f"{kind.keyword} {word}", COMPLETES, complete=f"{word} ")


def completion_rows(con, kind: Kind, ctx: Context, typed: str) -> tuple:
    prefix = partial_word(typed)
    if not prefix or offers(con, kind, ctx, prefix):
        return ()
    completed = [word for word in command_words(kind) if word.startswith(prefix) and offers(con, kind, ctx, word)]
    return tuple(completion_head(kind, word) for word in completed)


def command_or_search_rows(con: sqlite3.Connection, kind: Kind, ctx: Context, typed: str) -> tuple:
    word, rest = _search.split_command(typed)
    if offers_optional(con, kind, ctx, word):
        return OPTIONAL_COMMANDS[word][1](con, kind, ctx, rest)
    if _search.is_empty(con):
        return _rows.empty_index_rows(kind, ctx)
    if word in KERNEL_COMMANDS:
        return KERNEL_COMMANDS[word](con, kind, ctx, rest)
    if word in kind.commands:
        return command_rows(con, kind, ctx, word, rest)
    return search_rows(con, kind, ctx, typed)


def rows_for(con: sqlite3.Connection, kind: Kind, ctx: Context, typed: str) -> tuple:
    return completion_rows(con, kind, ctx, typed) + command_or_search_rows(con, kind, ctx, typed)

