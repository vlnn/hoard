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
