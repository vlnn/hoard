from __future__ import annotations

import pytest

from hoard import api
from hoard.render import text
from hoard.testing import FakeKind
from hoard.testing.fake import write_note


def lines(typed, ctx):
    return text.render(api.filter(FakeKind, typed, ctx))


@pytest.fixture
def library(ctx, shelf):
    write_note(shelf, "dune", "Dune", "Frank Herbert", "1965", mtime=3000)
    write_note(shelf, "messiah", "Dune Messiah", "Frank Herbert", "1969", mtime=2000)
    write_note(shelf, "eyre", "Jane Eyre", "Charlotte Brontë", "1847", mtime=1000)
    write_note(shelf, "ubik", "Ubik", "Philip K. Dick", "1969", mtime=4000)
    api.update(FakeKind, ctx)
    return ctx


def row(title, author, year, name, shelf):
    return f"{title} | shelf · {author} · {year} · {shelf}/{name}.note"


def test_an_empty_index_offers_to_update(ctx):
    assert lines("", ctx) == ["» Index is empty | ↩ to update the index"], "an empty index should say so"


def test_an_empty_index_says_so_whatever_is_typed(ctx):
    assert lines("dune", ctx) == ["» Index is empty | ↩ to update the index"], "searching nothing should not pretend"


@pytest.mark.parametrize(
    "typed, expected",
    [
        ("dune", [("Dune", "Frank Herbert", "1965", "dune"), ("Dune Messiah", "Frank Herbert", "1969", "messiah")]),
        ("DUNE", [("Dune", "Frank Herbert", "1965", "dune"), ("Dune Messiah", "Frank Herbert", "1969", "messiah")]),
        ("du mess", [("Dune Messiah", "Frank Herbert", "1969", "messiah")]),
        ("herb", [("Dune", "Frank Herbert", "1965", "dune"), ("Dune Messiah", "Frank Herbert", "1969", "messiah")]),
        ("bronte", [("Jane Eyre", "Charlotte Brontë", "1847", "eyre")]),
        ("Brontë eyre", [("Jane Eyre", "Charlotte Brontë", "1847", "eyre")]),
        ("1969", [("Ubik", "Philip K. Dick", "1969", "ubik"), ("Dune Messiah", "Frank Herbert", "1969", "messiah")]),
        ("k. dick", [("Ubik", "Philip K. Dick", "1969", "ubik")]),
    ],
)
def test_words_prefix_match_titles_and_fields_newest_first(library, shelf, typed, expected):
    assert lines(typed, library) == [row(*e, shelf) for e in expected], (
        f"{typed!r} should prefix-match every word, fold case and diacritics, and list newest first"
    )


def test_nothing_typed_lists_everything_newest_first(library, shelf):
    assert lines("", library) == [
        row("Ubik", "Philip K. Dick", "1969", "ubik", shelf),
        row("Dune", "Frank Herbert", "1965", "dune", shelf),
        row("Dune Messiah", "Frank Herbert", "1969", "messiah", shelf),
        row("Jane Eyre", "Charlotte Brontë", "1847", "eyre", shelf),
    ], "an empty query should list the newest entities"


@pytest.mark.parametrize("typed", ["zzz", "dune zzz", "—"])
def test_no_match_says_what_was_typed(library, typed):
    assert lines(typed, library) == [f"» No match for {typed}"], "an empty result should echo the query"


@pytest.mark.parametrize("typed", ["update", "update ", "Update"])
def test_update_word_offers_the_update_row(library, typed):
    assert lines(typed, library) == ["» Update the index | ↩ to read every storage again"], (
        "the update command should show its head row"
    )


def test_results_stop_at_forty(ctx, shelf):
    for n in range(45):
        write_note(shelf, f"n{n}", f"Note {n}", mtime=1000 + n)
    api.update(FakeKind, ctx)
    assert len(lines("note", ctx)) == 40, "a search should list at most forty rows"


def record_job(ctx, job, done, total):
    from hoard import _db, _progress

    con = _db.connect(_db.path_for(FakeKind.name, ctx.data))
    _progress.begin(con, job, total)
    _progress.advance(con, done)
    con.close()


@pytest.mark.parametrize(
    "job, done, total, head",
    [
        ("update", 4, 4, "» Updating the index… | 4 of 4 checked"),
        ("update", 0, "", "» Updating the index… | counting files"),
        ("ask", 120, 2150, "» Asking the model… | 120 of 2150 asked"),
        ("embed", 16, 2150, "» Embedding… | 16 of 2150 embedded"),
    ],
)
def test_a_running_worker_leads_with_its_own_job_and_reruns(library, mocker, job, done, total, head):
    mocker.patch("hoard._worker.running", return_value=True)
    record_job(library, job, done, total)
    items = api.filter(FakeKind, "ubik", library)
    assert text.render(items)[0] == head, f"a running {job} should say what it is doing, out of its own total"
    assert items.rerun == 1, "the filter should rerun while the worker runs"


def test_an_update_shows_its_progress_once_finished_reading(library, mocker):
    mocker.patch("hoard._worker.running", return_value=True)
    assert text.render(api.filter(FakeKind, "ubik", library))[0] == "» Updating the index… | 4 of 4 checked", (
        "a real update should leave every file it read counted out of the total"
    )


def test_rows_act_with_the_kinds_default_verb(library):
    (item,) = api.filter(FakeKind, "ubik", library).rows
    assert item.verb == "open", "a row should carry the kind's default verb"

