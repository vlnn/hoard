from __future__ import annotations

import pytest

from hoard import _journal
from hoard.contract import Change

COPY = (Change("id1", "copy", "/shelf/a", "/satchel/a"), Change("id2", "copy", "/shelf/b", "/satchel/b"))
TOSS = (Change("id1", "toss", None, None),)


def test_a_fresh_database_has_the_journal_kind_of_change(tmp_db):
    columns = [row[1] for row in tmp_db.execute("PRAGMA table_info(journal)")]
    assert "kind_of_change" in columns, "the journal should record what kind of change each row was"


def test_batches_are_numbered_in_order(tmp_db):
    numbers = [_journal.record(tmp_db, "pack", COPY, undoable=True) for _ in range(3)]
    assert numbers == [1, 2, 3], "each recorded batch should get the next number"


@pytest.mark.parametrize(
    "changes",
    [
        COPY,
        (Change("id1", "tag", ["old", "tags"], {"new": 1}),),
        (Change("id1", "rename", "Ä café.epub", "Ö café.epub"),),
    ],
)
def test_changes_come_back_as_they_went_in(tmp_db, changes):
    _journal.record(tmp_db, "pack", changes, undoable=True)
    batch = _journal.last_undoable(tmp_db)
    assert (batch.verb, batch.changes) == ("pack", changes), "the journal should hand back the same plain values"


def test_last_undoable_skips_batches_that_cannot_be_undone(tmp_db):
    first = _journal.record(tmp_db, "pack", COPY, undoable=True)
    _journal.record(tmp_db, "toss", TOSS, undoable=False)
    assert _journal.last_undoable(tmp_db).number == first, "undo should reach past a batch that cannot be undone"


def test_nothing_to_undo_on_an_empty_journal(tmp_db):
    assert _journal.last_undoable(tmp_db) is None, "an empty journal has nothing to undo"


def test_forgetting_a_batch_reveals_the_one_before(tmp_db):
    first = _journal.record(tmp_db, "pack", COPY, undoable=True)
    second = _journal.record(tmp_db, "pack", COPY[:1], undoable=True)
    _journal.forget(tmp_db, second)
    assert _journal.last_undoable(tmp_db).number == first, "after an undo the previous batch should be next"
