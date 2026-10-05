from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import time
from typing import Callable, Iterator, NamedTuple, Optional

from hoard import _db, _fold, _icons, _names
from hoard._text import refresh_text
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


def digest(text: str) -> str:
    return hashlib.blake2b(text.encode("utf-8"), digest_size=16).hexdigest()


def text_hash(entity: Entity) -> str:
    return digest(entity.text)


def evidence_of(kind: Kind, entity: Entity) -> str:
    try:
        return kind.evidence(entity)
    except Exception as error:
        print(f"evidence: {entity.title}: {error!r}", file=sys.stderr)
        return ""


FAILED = object()

MISSING = """
SELECT e.id, e.title, e.fields_json, e.icon FROM entities e
WHERE NOT EXISTS (SELECT 1 FROM derived d WHERE d.id = e.id AND d.key = ?)
"""


def store_sighting(con: sqlite3.Connection, storage: str, entity: Entity, path: str, stat: os.stat_result) -> None:
    con.execute(
        "INSERT OR REPLACE INTO sightings(id, storage, locator, mtime, size) VALUES (?, ?, ?, ?, ?)",
        (entity.id, storage, path, stat.st_mtime, stat.st_size),
    )


def store_entity(run: Run, entity: Entity, stat: os.stat_result) -> None:
    evidence = evidence_of(run.kind, entity)
    run.con.execute(
        """
        INSERT INTO entities(id, title, fields_json, icon, size, mtime, text_hash, first_seen, last_seen, evidence, evidence_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            title = excluded.title, fields_json = excluded.fields_json, icon = excluded.icon,
            size = excluded.size, text_hash = excluded.text_hash, last_seen = excluded.last_seen,
            evidence = excluded.evidence, evidence_hash = excluded.evidence_hash
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
            evidence,
            digest(evidence),
        ),
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
    _names.overlay(run.con, run.kind, entity.id)
    refresh_text(run.con, entity.id)
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


def unrooted(con: sqlite3.Connection, storage: str, configured: list) -> list:
    rows = con.execute("SELECT locator FROM sightings WHERE storage = ? AND locator IS NOT NULL", (storage,))
    return [(storage, locator) for (locator,) in rows if not any(_fold.under(locator, root) for root in configured)]


def forget_unrooted(con: sqlite3.Connection, storage: str, configured: list) -> None:
    con.executemany("DELETE FROM sightings WHERE storage = ? AND locator = ?", unrooted(con, storage, configured))


def update_storage(run: Run, storage: Storage) -> None:
    run.start_storage()
    configured = list(storage.roots(run.ctx))
    roots = [root for root in configured if storage.mounted(root)]
    for root in roots:
        update_root(run, storage, root)
    forget_unrooted(run.con, storage.name, configured)
    record_state(run.con, storage.name, bool(roots))
    run.on_progress(run.found)


def drop_orphans(con: sqlite3.Connection) -> None:
    orphans = "SELECT rowid FROM entities WHERE id NOT IN (SELECT id FROM sightings)"
    con.execute(f"DELETE FROM fts WHERE rowid IN ({orphans})")
    con.execute(f"DELETE FROM entities WHERE rowid IN ({orphans})")


def settle_mtimes(con: sqlite3.Connection) -> None:
    con.execute("UPDATE entities SET mtime = (SELECT max(s.mtime) FROM sightings s WHERE s.id = entities.id)")


def produce(key: str, producer, found, ctx: Context):
    try:
        return producer(found, ctx) or ""
    except Exception as error:
        print(f"derive {key}: {found.entity.title}: {error!r}", file=sys.stderr)
        return FAILED


def store_derived(con: sqlite3.Connection, entity_id: str, key: str, value: str) -> None:
    con.execute(
        "INSERT OR REPLACE INTO derived(id, key, value, source, made_at) VALUES (?, ?, ?, ?, ?)",
        (entity_id, key, value, key, time.time()),
    )
    refresh_text(con, entity_id)


def derive_missing(run: Run) -> None:
    for key, producer in run.kind.derive.items():
        rows = run.con.execute(MISSING, (key,)).fetchall()
        for row in _fold.fold(run.con, run.kind, run.ctx, rows):
            value = produce(key, producer, row.found, run.ctx)
            if value is not FAILED:
                store_derived(run.con, row.found.entity.id, key, value)


def make_local_vectors(con: sqlite3.Connection, kind: Kind, ctx: Context) -> None:
    from hoard import _embed

    if _embed.is_local(kind):
        _embed.run_local(con, kind, ctx)


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
    make_local_vectors(con, kind, ctx)
    derive_missing(run)
    con.commit()
    return run.found
