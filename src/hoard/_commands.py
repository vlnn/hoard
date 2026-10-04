from __future__ import annotations

import sqlite3

from hoard import _rows, _search
from hoard.contract import Kind


def update_rows(con: sqlite3.Connection, kind: Kind, words: list) -> tuple:
    return (_rows.update_offer(),)


KERNEL_COMMANDS = {"update": update_rows}


def search_rows(con: sqlite3.Connection, kind: Kind, typed: str) -> tuple:
    if _search.is_empty(con):
        return (_rows.index_empty(),)
    found = tuple(_rows.entity_item(kind, row) for row in _search.search(con, typed))
    return found or (_rows.no_match(typed),)


def rows_for(con: sqlite3.Connection, kind: Kind, typed: str) -> tuple:
    word, rest = _search.split_command(typed)
    command = KERNEL_COMMANDS.get(word)
    return command(con, kind, rest) if command else search_rows(con, kind, typed)


def found_so_far(con: sqlite3.Connection) -> int:
    (total,) = con.execute("SELECT coalesce(sum(count), 0) FROM storage_state").fetchone()
    return total
