from __future__ import annotations

import pytest

from hoard import _db


def table_names(con):
    rows = con.execute("SELECT name FROM sqlite_master WHERE type IN ('table')").fetchall()
    return {name for (name,) in rows}


def test_a_new_database_is_at_the_latest_schema(tmp_db):
    assert _db.schema_version(tmp_db) == len(_db.MIGRATIONS), "a fresh database should be fully migrated"


@pytest.mark.parametrize("table", sorted(_db.CACHE_TABLES | _db.STORE_TABLES | {"meta"}))
def test_every_table_in_the_plan_exists(tmp_db, table):
    assert table in table_names(tmp_db), f"{table} should be created by the schema"


def test_cache_and_store_halves_do_not_overlap():
    assert not _db.CACHE_TABLES & _db.STORE_TABLES, "a table should belong to exactly one half"


def test_reconnecting_does_not_migrate_twice(tmp_path):
    path = str(tmp_path / "k.sqlite")
    _db.connect(path).close()
    con = _db.connect(path)
    assert _db.schema_version(con) == len(_db.MIGRATIONS), "reopening should keep the schema version"
    con.close()


def test_database_uses_write_ahead_logging(tmp_db):
    (mode,) = tmp_db.execute("PRAGMA journal_mode").fetchone()
    assert mode == "wal", "the worker writes while the filter reads, so the journal should be WAL"


def test_drop_cache_keeps_store_tables(tmp_db):
    tmp_db.execute("INSERT INTO tags VALUES ('id1', 'scifi', 'hand', 1.0)")
    tmp_db.execute("INSERT INTO entities(id, title, fields_json) VALUES ('id1', 'Dune', '[]')")
    _db.drop_cache(tmp_db)
    assert tmp_db.execute("SELECT count(*) FROM entities").fetchone() == (0,), "cache tables should be emptied"
    assert tmp_db.execute("SELECT count(*) FROM tags").fetchone() == (1,), "store tables should survive"


def test_a_version_one_database_migrates_and_keeps_its_journal(tmp_path):
    import sqlite3

    path = str(tmp_path / "old.sqlite")
    old = sqlite3.connect(path)
    old.executescript(_db.SCHEMA_V1)
    old.execute("INSERT INTO meta VALUES ('schema_version', '1')")
    old.execute("INSERT INTO journal(batch, seq, verb, id) VALUES (1, 0, 'pack', 'id1')")
    old.commit()
    old.close()
    con = _db.connect(path)
    assert _db.schema_version(con) == len(_db.MIGRATIONS), "an old database should be migrated on connect"
    assert con.execute("SELECT verb, kind_of_change FROM journal").fetchall() == [("pack", None)], (
        "migration should keep the journal and add the new column empty"
    )
    con.close()


def test_version_two_sightings_survive_the_rekey(tmp_path):
    import sqlite3

    path = str(tmp_path / "v2.sqlite")
    old = sqlite3.connect(path)
    old.executescript(_db.SCHEMA_V1)
    old.executescript(_db.JOURNAL_KIND_OF_CHANGE)
    old.execute("INSERT INTO meta VALUES ('schema_version', '2')")
    old.execute("INSERT INTO sightings VALUES ('id1', 'shelf', '/shelf/a', 1.0, 3)")
    old.commit()
    old.close()
    con = _db.connect(path)
    assert con.execute("SELECT id, storage, locator, size FROM sightings").fetchall() == [("id1", "shelf", "/shelf/a", 3)], (
        "rekeying sightings should keep every row"
    )
    con.execute("INSERT INTO sightings VALUES ('id1', 'shelf', '/shelf/b', 1.0, 3)")
    assert con.execute("SELECT count(*) FROM sightings").fetchone() == (2,), "one entity may now sit twice in a storage"
    con.close()


def test_version_four_adds_evidence_and_asks_for_a_reread(tmp_path):
    import sqlite3

    path = str(tmp_path / "v3.sqlite")
    old = sqlite3.connect(path)
    for script in _db.MIGRATIONS[:3]:
        old.executescript(script)
    old.execute("INSERT INTO meta VALUES ('schema_version', '3')")
    old.execute("INSERT INTO sightings VALUES ('id1', 'shelf', '/shelf/a', 1.0, 3)")
    old.commit()
    old.close()
    con = _db.connect(path)
    columns = [row[1] for row in con.execute("PRAGMA table_info(entities)")]
    assert {"evidence", "evidence_hash"} <= set(columns), "entities should carry evidence and its hash"
    assert con.execute("SELECT mtime FROM sightings").fetchone() == (-1,), "every file should look changed once"
    con.close()


def test_version_five_keeps_vectors_unsigned_and_drops_neighbours(tmp_path):
    import sqlite3

    path = str(tmp_path / "v4.sqlite")
    old = sqlite3.connect(path)
    for script in _db.MIGRATIONS[:4]:
        old.executescript(script)
    old.execute("INSERT INTO meta VALUES ('schema_version', '4')")
    old.execute("INSERT INTO vectors VALUES ('m', 'id1', x'0000803f')")
    old.execute("INSERT INTO neighbours VALUES ('m', 'id1', 0, 'id2', 0.9)")
    old.commit()
    old.close()
    con = _db.connect(path)
    assert "neighbours" not in table_names(con), "neighbours should be gone; like ranks when asked"
    assert con.execute("SELECT id, sig FROM vectors").fetchall() == [("id1", None)], (
        "old vectors should stay, unsigned, until they are made again"
    )
    con.close()


def test_a_migration_rereads_the_version_once_it_holds_the_write_lock(tmp_path, mocker):
    import sqlite3

    path = str(tmp_path / "k.sqlite")
    _db.connect(path).close()
    latest = _db.schema_version
    stale = iter([1])
    mocker.patch("hoard._db.schema_version", side_effect=lambda con: next(stale, None) or latest(con))
    con = sqlite3.connect(path)
    _db.migrate(con)
    assert latest(con) == len(_db.MIGRATIONS), "a version read before another process migrated should not migrate again"
    con.close()


def test_a_failing_migration_leaves_the_database_at_its_old_version(tmp_path, mocker):
    import sqlite3

    path = str(tmp_path / "k.sqlite")
    _db.connect(path).close()
    mocker.patch("hoard._db.MIGRATIONS", (*_db.MIGRATIONS, "CREATE TABLE extra(x);\nCREATE TABLE extra(x);"))
    con = sqlite3.connect(path)
    with pytest.raises(sqlite3.OperationalError):
        _db.migrate(con)
    con.close()
    reopened = sqlite3.connect(path)
    assert _db.schema_version(reopened) == len(_db.MIGRATIONS) - 1, "a failed migration should not bump the version"
    assert "extra" not in table_names(reopened), "a failed migration should leave nothing half applied"
    reopened.close()


@pytest.mark.parametrize("attempt", range(5))
def test_connections_racing_to_a_new_database_all_succeed(tmp_path, attempt):
    import sqlite3
    import threading

    path = str(tmp_path / "k.sqlite")
    start = threading.Barrier(8)
    errors = []

    def connecting():
        start.wait()
        try:
            _db.connect(path).close()
        except sqlite3.Error as error:
            errors.append(error)

    threads = [threading.Thread(target=connecting) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == [], "the filter and the worker opening a new database together should both get the full schema"
    con = _db.connect(path)
    (mode,) = con.execute("PRAGMA journal_mode").fetchone()
    con.close()
    assert mode == "wal", "a switch to WAL lost in the race should be made by the next connection"


def test_a_busy_database_still_connects_and_switches_to_wal_later(tmp_path):
    import sqlite3

    path = str(tmp_path / "k.sqlite")
    writer = sqlite3.connect(path)
    writer.execute("CREATE TABLE held(x)")
    writer.commit()
    writer.execute("BEGIN IMMEDIATE")
    reader = sqlite3.connect(path, timeout=0)
    _db.write_ahead(reader)
    writer.rollback()
    _db.write_ahead(reader)
    (mode,) = reader.execute("PRAGMA journal_mode").fetchone()
    reader.close()
    writer.close()
    assert mode == "wal", "a locked switch should be skipped quietly and done on a later try"


def test_the_covered_first_order_is_served_by_an_index(tmp_db):
    plan = " ".join(row[-1] for row in tmp_db.execute(f"EXPLAIN QUERY PLAN SELECT rowid FROM entities ORDER BY {_db.COVERED_FIRST} LIMIT 40"))
    assert "entities_covered_newest" in plan and "TEMP B-TREE" not in plan, (
        "listing covered books first, newest first, should read an index rather than sort the table"
    )
