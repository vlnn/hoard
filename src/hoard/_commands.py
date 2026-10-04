from __future__ import annotations

import sqlite3
import time

import hoard
from hoard import _db, _fold, _journal, _rows, _search
from hoard.contract import Command, Context, Kind, everything
from hoard.items import Head

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
    return tuple(_rows.entity_item(kind, row) for row in _fold.fold(con, kind, ctx, entity_rows))


def update_rows(con, kind, ctx, words) -> tuple:
    return (_rows.update_offer(),)


def verb_label(kind: Kind, verb: str) -> str:
    return kind.verbs[verb].label if verb in kind.verbs else verb


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
        Head("stats", plural(entities, "entity", "entities")),
        *(storage_head(con, s.name, mounted[s.name]) for s in kind.storages),
        Head("stats:hoard", f"hoard {hoard.__version__}", f"schema v{_db.schema_version(con)}"),
    )


KERNEL_COMMANDS = {"update": update_rows, "undo": undo_rows, "rnd": rnd_rows, "stats": stats_rows}


def final(kind: Kind, verb: str) -> bool:
    return verb in kind.verbs and not kind.verbs[verb].undoable


def in_sql_only(command: Command) -> bool:
    return command.keep is everything


def batch_head(kind: Kind, batch: str, command: Command, total: int) -> Head:
    subtitle = "↩ on every row below" + (" · cannot be undone" if final(kind, command.verb) else "")
    return Head("batch", f"{command.label} all {total}", subtitle, verb=command.verb, batch=batch)


def kept_rows(con, kind: Kind, ctx: Context, command: Command, typed: str) -> list:
    every = _search.search(con, typed, _search.EVERYTHING, command.on, command.off)
    return [row for row in _fold.fold(con, kind, ctx, every) if command.keep(row.found)]


def shown_and_total(con, kind: Kind, ctx: Context, command: Command, typed: str) -> tuple:
    if in_sql_only(command):
        shown = _fold.fold(con, kind, ctx, _search.search(con, typed, _search.LIMIT, command.on, command.off))
        return shown, _search.count(con, typed, command.on, command.off)
    kept = kept_rows(con, kind, ctx, command, typed)
    return kept[: _search.LIMIT], len(kept)


def command_rows(con, kind: Kind, ctx: Context, word: str, words: list) -> tuple:
    command, typed = kind.commands[word], " ".join(words)
    shown, total = shown_and_total(con, kind, ctx, command, typed)
    if not total:
        return (Head("none", f"Nothing to {command.label.lower()}"),)
    head = batch_head(kind, " ".join([word, *words]).lower(), command, total)
    return (head,) + tuple(_rows.entity_item(kind, row, command.verb) for row in shown)


def batch_ids(con, kind: Kind, ctx: Context, batch: str) -> list:
    word, words = _search.split_command(batch)
    command, typed = kind.commands.get(word), " ".join(words)
    if command is None:
        return []
    if in_sql_only(command):
        return _search.ids(con, typed, command.on, command.off)
    return [row.found.entity.id for row in kept_rows(con, kind, ctx, command, typed)]


def search_rows(con, kind: Kind, ctx: Context, typed: str) -> tuple:
    found = items_for(con, kind, ctx, _search.search(con, typed))
    return found or (_rows.no_match(typed),)


def rows_for(con: sqlite3.Connection, kind: Kind, ctx: Context, typed: str) -> tuple:
    word, rest = _search.split_command(typed)
    if word == "update":
        return update_rows(con, kind, ctx, rest)
    if _search.is_empty(con):
        return _rows.empty_index_rows(kind, ctx)
    if word in KERNEL_COMMANDS:
        return KERNEL_COMMANDS[word](con, kind, ctx, rest)
    if word in kind.commands:
        return command_rows(con, kind, ctx, word, rest)
    return search_rows(con, kind, ctx, typed)


def found_so_far(con: sqlite3.Connection) -> int:
    (total,) = con.execute("SELECT coalesce(sum(count), 0) FROM storage_state").fetchone()
    return total
