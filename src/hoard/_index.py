from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import time
from typing import Callable, Iterator, NamedTuple, Optional

from hoard import _db, _icons
from hoard.contract import Context, Entity, Kind, Storage

BATCH = 200


def ignore_progress(found: int) -> None:
    pass


class Known(NamedTuple):
    id: str
    mtime: float
    size: int

    def unchanged(self, stat: os.stat_result) -> bool:
        return (self.mtime, self.size) == (stat.st_mtime, stat.st_size)


class Run:
    def __init__(self, con: sqlite3.Connection, kind: Kind, ctx: Context, number: int, on_progress: Callable[[int], None]):
        self.con, self.kind, self.ctx, self.number, self.on_progress = con, kind, ctx, number, on_progress
        self.found = 0
        self.found_in_storage = 0

    def start_storage(self) -> None:
        self.found_in_storage = 0

    def found_one(self, storage: Storage) -> None:
        self.found += 1
        self.found_in_storage += 1
        if self.found % BATCH == 0:
            record_progress(self.con, storage.name, self.found_in_storage)
            self.con.commit()
            self.on_progress(self.found)


def hidden(name: str) -> bool:
    return name.startswith(".")


def walk(root: str) -> Iterator[tuple]:
    for folder, folders, files in os.walk(root):
        folders[:] = sorted(name for name in folders if not hidden(name))
        for name in sorted(files):
            if hidden(name):
                continue
            path = os.path.join(folder, name)
            try:
                yield path, os.stat(path)
            except OSError:
                continue


def next_run(con: sqlite3.Connection) -> int:
    number = int(_db.meta(con, "update_run", "0")) + 1
    _db.set_meta(con, "update_run", str(number))
    return number


def known_files(con: sqlite3.Connection, storage: str, root: str) -> dict:
    prefix = root.rstrip(os.sep) + os.sep
    rows = con.execute(
        "SELECT locator, id, mtime, size FROM sightings WHERE storage = ? AND substr(locator, 1, ?) = ?",
        (storage, len(prefix), prefix),
    )
    return {locator: Known(entity_id, mtime, size) for locator, entity_id, mtime, size in rows}


def read_safely(storage: Storage, path: str) -> Optional[Entity]:
    try:
        return storage.reader(path)
    except Exception as error:
        print(f"{storage.name}: cannot read {path}: {error!r}", file=sys.stderr)
        return None


def text_hash(entity: Entity) -> str:
    return hashlib.blake2b(entity.text.encode("utf-8"), digest_size=16).hexdigest()


def fts_body(entity: Entity) -> str:
    return "\n".join(value for value in entity.fields if value)


def store_sighting(con: sqlite3.Connection, storage: str, entity: Entity, path: str, stat: os.stat_result) -> None:
    con.execute(
        "INSERT OR REPLACE INTO sightings(id, storage, locator, mtime, size) VALUES (?, ?, ?, ?, ?)",
        (entity.id, storage, path, stat.st_mtime, stat.st_size),
    )


def store_entity(run: Run, entity: Entity, stat: os.stat_result) -> None:
    run.con.execute(
        """
        INSERT INTO entities(id, title, fields_json, icon, size, mtime, text_hash, first_seen, last_seen)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            title = excluded.title, fields_json = excluded.fields_json, icon = excluded.icon,
            size = excluded.size, text_hash = excluded.text_hash, last_seen = excluded.last_seen
        """,
        (
            entity.id,
            entity.title,
            json.dumps(list(entity.fields), ensure_ascii=False),
            _icons.icon_for(run.kind, entity, run.ctx.cache),
            stat.st_size,
            stat.st_mtime,
            text_hash(entity),
            run.number,
            run.number,
        ),
    )


def store_text(con: sqlite3.Connection, entity: Entity) -> None:
    (rowid,) = con.execute("SELECT rowid FROM entities WHERE id = ?", (entity.id,)).fetchone()
    con.execute("DELETE FROM fts WHERE rowid = ?", (rowid,))
    con.execute(
        "INSERT INTO fts(rowid, id, title, body) VALUES (?, ?, ?, ?)",
        (rowid, entity.id, entity.title, fts_body(entity)),
    )


def touch(run: Run, entity_id: str) -> None:
    run.con.execute("UPDATE entities SET last_seen = ? WHERE id = ?", (run.number, entity_id))


def index_file(run: Run, storage: Storage, path: str, stat: os.stat_result, known: Optional[Known]) -> bool:
    if known and known.unchanged(stat):
        touch(run, known.id)
        return True
    entity = read_safely(storage, path)
    if entity is None:
        return False
    store_sighting(run.con, storage.name, entity, path, stat)
    store_entity(run, entity, stat)
    store_text(run.con, entity)
    return True


def forget(con: sqlite3.Connection, storage: str, locators) -> None:
    con.executemany(
        "DELETE FROM sightings WHERE storage = ? AND locator = ?",
        [(storage, locator) for locator in locators],
    )


def update_root(run: Run, storage: Storage, root: str) -> None:
    known = known_files(run.con, storage.name, root)
    seen = set()
    for path, stat in walk(root):
        seen.add(path)
        if index_file(run, storage, path, stat, known.get(path)):
            run.found_one(storage)
    forget(run.con, storage.name, set(known) - seen)


def record_progress(con: sqlite3.Connection, storage: str, count: int) -> None:
    con.execute(
        "INSERT INTO storage_state(storage, count) VALUES (?, ?) ON CONFLICT(storage) DO UPDATE SET count = excluded.count",
        (storage, count),
    )


def record_state(con: sqlite3.Connection, storage: str, mounted: bool) -> None:
    now = time.time()
    con.execute(
        """
        INSERT OR REPLACE INTO storage_state(storage, mounted, checked_at, last_update_at, count)
        VALUES (?, ?, ?, ?, (SELECT count(*) FROM sightings WHERE storage = ?))
        """,
        (storage, int(mounted), now, now, storage),
    )


def update_storage(run: Run, storage: Storage) -> None:
    run.start_storage()
    roots = [root for root in storage.roots(run.ctx) if storage.mounted(root)]
    for root in roots:
        update_root(run, storage, root)
    record_state(run.con, storage.name, bool(roots))
    run.on_progress(run.found)


def drop_orphans(con: sqlite3.Connection) -> None:
    orphans = "SELECT rowid FROM entities WHERE id NOT IN (SELECT id FROM sightings)"
    con.execute(f"DELETE FROM fts WHERE rowid IN ({orphans})")
    con.execute(f"DELETE FROM entities WHERE rowid IN ({orphans})")


def settle_mtimes(con: sqlite3.Connection) -> None:
    con.execute("UPDATE entities SET mtime = (SELECT max(s.mtime) FROM sightings s WHERE s.id = entities.id)")


def start(con: sqlite3.Connection, full: bool) -> int:
    if full:
        _db.drop_cache(con)
    con.execute("UPDATE storage_state SET count = 0")
    return next_run(con)


def update(
    con: sqlite3.Connection,
    kind: Kind,
    ctx: Context,
    on_progress: Callable[[int], None] = ignore_progress,
    full: bool = False,
) -> int:
    run = Run(con, kind, ctx, start(con, full), on_progress)
    for storage in kind.storages:
        update_storage(run, storage)
    drop_orphans(con)
    settle_mtimes(con)
    con.commit()
    return run.found
