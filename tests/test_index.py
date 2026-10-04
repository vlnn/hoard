from __future__ import annotations

import os

import pytest

from hoard import _db, _index
from hoard.testing import FakeKind
from hoard.testing.fake import read_note, write_note


def entity_titles(con):
    return sorted(title for (title,) in con.execute("SELECT title FROM entities"))


def with_reader(kind, reader):
    return kind._replace(storages=tuple(s._replace(reader=reader) for s in kind.storages))


def with_icon(kind, icon):
    return kind._replace(icon=icon)


@pytest.fixture
def three_notes(shelf):
    return [
        write_note(shelf, "dune", "Dune", "Frank Herbert", "1965"),
        write_note(shelf, "eyre", "Jane Eyre", "Charlotte Brontë", "1847"),
        write_note(shelf, "deep/ubik", "Ubik", "Philip K. Dick", "1969"),
    ]


def test_update_indexes_every_readable_file(tmp_db, ctx, three_notes):
    _index.update(tmp_db, FakeKind, ctx)
    assert entity_titles(tmp_db) == ["Dune", "Jane Eyre", "Ubik"], "every note should become an entity"


@pytest.mark.parametrize(
    "name",
    ["cover.jpg", ".hidden/dune.note", ".hoard-trash/old.note", "notes/.dune.note"],
)
def test_update_skips_unreadable_and_hidden_files(tmp_db, ctx, shelf, name, temp_tree):
    temp_tree({name: "title: Ghost\n\n"}, root="shelf")
    _index.update(tmp_db, FakeKind, ctx)
    assert entity_titles(tmp_db) == [], f"{name} should not be indexed"


def test_second_update_reads_only_changed_files(tmp_db, ctx, three_notes, mocker):
    reader = mocker.Mock(wraps=read_note)
    kind = with_reader(FakeKind, reader)
    _index.update(tmp_db, kind, ctx)
    reader.reset_mock()
    write_note(os.path.dirname(three_notes[0]), "dune", "Dune Messiah", "Frank Herbert", "1969")
    _index.update(tmp_db, kind, ctx)
    reader.assert_called_once_with(three_notes[0])
    assert "Dune Messiah" in entity_titles(tmp_db), "a changed file should be re-read"


def test_a_deleted_file_leaves_the_index(tmp_db, ctx, three_notes):
    _index.update(tmp_db, FakeKind, ctx)
    os.remove(three_notes[1])
    _index.update(tmp_db, FakeKind, ctx)
    assert entity_titles(tmp_db) == ["Dune", "Ubik"], "a vanished file should drop its entity"


def test_an_unmounted_storage_keeps_its_sightings(tmp_db, context_with, shelf, three_notes, tmp_path):
    _index.update(tmp_db, FakeKind, context_with(fake_shelf=str(shelf)))
    os.rename(shelf, tmp_path / "unplugged")
    _index.update(tmp_db, FakeKind, context_with(fake_shelf=str(shelf)))
    assert len(entity_titles(tmp_db)) == 3, "an unmounted root should not erase what was seen on it"


def test_the_same_entity_in_two_storages_is_one_entity(tmp_db, ctx, shelf, satchel):
    write_note(shelf, "dune", "Dune", "Frank Herbert", "1965")
    write_note(satchel, "dune copy", "Dune", "Frank Herbert", "1965")
    _index.update(tmp_db, FakeKind, ctx)
    assert entity_titles(tmp_db) == ["Dune"], "identical content should be one entity"
    assert tmp_db.execute("SELECT count(*) FROM sightings").fetchone() == (2,), "each storage should record a sighting"


def test_entity_mtime_is_the_newest_sighting(tmp_db, ctx, shelf, satchel):
    write_note(shelf, "dune", "Dune", mtime=1000)
    write_note(satchel, "dune", "Dune", mtime=2000)
    _index.update(tmp_db, FakeKind, ctx)
    assert tmp_db.execute("SELECT mtime FROM entities").fetchone() == (2000,), "newest first should use the newest copy"


def test_a_cover_is_written_to_the_cache_folder(tmp_db, ctx, shelf):
    path = write_note(shelf, "dune", "Dune")
    jpeg = b"\xff\xd8\xff\xe0cover"
    kind = with_reader(FakeKind, lambda p: read_note(p)._replace(cover=jpeg) if read_note(p) else None)
    _index.update(tmp_db, kind, ctx)
    (icon,) = tmp_db.execute("SELECT icon FROM entities").fetchone()
    assert icon == os.path.join(ctx.cache, "icons", read_note(path).id + ".jpg"), "the cover should be cached by id"
    with open(icon, "rb") as handle:
        assert handle.read() == jpeg, "the cached icon should hold the cover bytes"


def test_without_a_cover_the_kind_draws_the_icon(tmp_db, ctx, shelf):
    write_note(shelf, "dune", "Dune")
    _index.update(tmp_db, with_icon(FakeKind, lambda e: "icons/note.png"), ctx)
    assert tmp_db.execute("SELECT icon FROM entities").fetchone() == ("icons/note.png",), "the kind's icon is the fallback"


def test_a_reader_that_raises_does_not_stop_the_update(tmp_db, ctx, three_notes):
    def fragile(path):
        if path.endswith("dune.note"):
            raise ValueError("broken file")
        return read_note(path)

    _index.update(tmp_db, with_reader(FakeKind, fragile), ctx)
    assert entity_titles(tmp_db) == ["Jane Eyre", "Ubik"], "one bad file should be skipped, not fatal"


def test_progress_reports_files_checked(tmp_db, ctx, three_notes, mocker):
    progress = mocker.Mock()
    _index.update(tmp_db, FakeKind, ctx, on_progress=progress)
    progress.assert_called_with(3)


def test_storage_state_counts_sightings(tmp_db, ctx, three_notes):
    _index.update(tmp_db, FakeKind, ctx)
    counts = dict(tmp_db.execute("SELECT storage, count FROM storage_state"))
    assert counts == {"shelf": 3, "satchel": 0}, "each storage should record how many things it holds"


def kept_rows(con):
    return {table: sorted(con.execute(f"SELECT * FROM {table}")) for table in sorted(_db.KEPT_TABLES)}


def test_full_rebuild_leaves_kept_tables_byte_identical(tmp_db, ctx, three_notes):
    _index.update(tmp_db, FakeKind, ctx)
    tmp_db.execute("INSERT INTO tags VALUES ('id1', 'scifi', 'hand', 1.0)")
    tmp_db.execute("INSERT INTO derived VALUES ('id1', 'ocr', 'text', 'tesseract', 1.0)")
    tmp_db.commit()
    before = kept_rows(tmp_db)
    _index.update(tmp_db, FakeKind, ctx, full=True)
    assert kept_rows(tmp_db) == before, "a full rebuild should not touch store tables or derived values"
    assert entity_titles(tmp_db) == ["Dune", "Jane Eyre", "Ubik"], "a full rebuild should re-read every storage"


def test_reader_entity_keeps_its_fields(tmp_db, ctx, shelf):
    write_note(shelf, "dune", "Dune", "Frank Herbert", "1965")
    _index.update(tmp_db, FakeKind, ctx)
    (fields_json,) = tmp_db.execute("SELECT fields_json FROM entities").fetchone()
    assert fields_json == f'["Frank Herbert", "1965", "{shelf}/dune.note"]', "fields should be stored in kind order"


def test_identical_files_in_one_storage_are_two_sightings_of_one_entity(tmp_db, ctx, shelf, mocker):
    write_note(shelf, "dune", "Dune", "Frank Herbert", "1965")
    write_note(shelf, "copies/dune", "Dune", "Frank Herbert", "1965")
    reader = mocker.Mock(wraps=read_note)
    kind = with_reader(FakeKind, reader)
    _index.update(tmp_db, kind, ctx)
    assert entity_titles(tmp_db) == ["Dune"], "identical content should stay one entity"
    assert tmp_db.execute("SELECT count(*) FROM sightings").fetchone() == (2,), "each copy should be its own sighting"
    reader.reset_mock()
    _index.update(tmp_db, kind, ctx)
    reader.assert_not_called()


def test_update_stores_the_kinds_evidence_and_its_hash(tmp_db, ctx, shelf):
    import hashlib

    write_note(shelf, "dune", "Dune", "Frank Herbert", "1965", body="spice")
    _index.update(tmp_db, FakeKind, ctx)
    evidence, evidence_hash = tmp_db.execute("SELECT evidence, evidence_hash FROM entities").fetchone()
    assert evidence == "Dune\nFrank Herbert\n1965\nspice", "evidence should be what the kind says it is"
    assert evidence_hash == hashlib.blake2b(evidence.encode(), digest_size=16).hexdigest(), "the hash keys the answer cache"
