from __future__ import annotations

import os

import pytest

from hoard import __version__, _db, api
from hoard.contract import Command
from hoard.render import text
from hoard.testing import FakeKind
from hoard.testing.fake import write_note

TOSSING = FakeKind._replace(commands={"bin": Command("Toss", "toss")})


@pytest.fixture
def library(ctx, shelf, satchel):
    write_note(shelf, "dune", "Dune", "Frank Herbert", "1965", mtime=3000)
    write_note(shelf, "messiah", "Dune Messiah", "Frank Herbert", "1969", mtime=2000)
    write_note(shelf, "ubik", "Ubik", "Philip K. Dick", "1969", mtime=1000)
    write_note(satchel, "ubik", "Ubik", "Philip K. Dick", "1969", mtime=1000)
    api.update(FakeKind, ctx)
    return ctx


def lines(kind, ctx, typed):
    return text.render(api.filter(kind, typed, ctx))


def test_a_kind_command_lists_what_it_keeps_under_a_batch_row(library, shelf):
    assert lines(FakeKind, library, "loose") == [
        "» Pack all 2 | ↩ on every row below",
        f"Dune | shelf · Frank Herbert · 1965 · {shelf}/dune.note",
        f"Dune Messiah | shelf · Frank Herbert · 1969 · {shelf}/messiah.note",
    ], "loose should keep only what is not in the satchel, with one row to pack them all"


def test_command_words_narrow_its_rows(library):
    assert lines(FakeKind, library, "loose messiah")[0] == "» Pack all 1 | ↩ on every row below", (
        "words after the command should narrow what it keeps"
    )


def test_command_rows_and_batch_carry_its_verb_and_query(library):
    head, *rows = api.filter(FakeKind, "loose  Dune ", library).rows
    assert (head.verb, head.arg) == ("pack", "batch:loose dune"), "the batch row should carry the verb and the query"
    assert {row.verb for row in rows} == {"pack"}, "↩ on a command row should run the command's verb"


def test_acting_on_a_batch_runs_the_verb_on_everything_the_command_keeps(library, satchel):
    assert api.act(FakeKind, "pack", ["batch:loose"], library) == "Pack into the satchel: 2 notes", (
        "a batch should expand to every row the command keeps"
    )
    assert sorted(os.listdir(satchel)) == ["dune.note", "messiah.note", "ubik.note"], "both loose notes are packed"


def test_a_command_with_its_own_keep_filters_in_python(library):
    old = FakeKind._replace(commands={"old": Command("Toss", "toss", keep=lambda f: f.entity.fields[1] < "1966")})
    assert lines(old, library, "old")[:2] == ["» Toss all 1 | ↩ on every row below · cannot be undone", lines(old, library, "dune")[0]], (
        "keep should see every row and decide"
    )


def test_a_command_with_nothing_to_keep_says_so(library):
    assert lines(FakeKind, library, "loose ubik") == ["» Nothing to pack"], "an empty command should say so"


def test_a_batch_of_a_final_verb_warns(library):
    assert lines(TOSSING, library, "bin")[0] == "» Toss all 3 | ↩ on every row below · cannot be undone", (
        "a batch row for a verb without undo should say it is final"
    )


@pytest.mark.parametrize("typed", ["loose", "rnd", "stats", "undo"])
def test_commands_on_an_empty_index_explain_it(ctx, typed):
    assert lines(FakeKind, ctx, typed)[-1] == "» Index is empty | ↩ to update the index", (
        f"{typed} should not pretend there is data"
    )


def test_undo_command_names_the_last_batch(library):
    dune = api.filter(FakeKind, "dune", library).rows[0].id
    api.act(FakeKind, "pack", [dune], library)
    head = api.filter(FakeKind, "undo", library).rows[0]
    assert text.render(api.filter(FakeKind, "undo", library)) == ["» Undo Pack into the satchel | 1 change · just now"], (
        "the undo row should name the verb and size of the last batch"
    )
    assert head.verb == "undo", "↩ on the undo row should undo"


def test_undo_command_with_an_empty_journal(library):
    assert lines(FakeKind, library, "undo") == ["» Nothing to undo"], "with no batch the undo row should say so"


def test_rnd_lists_entities_in_some_order(library):
    titles = sorted(line.split(" | ")[0] for line in lines(FakeKind, library, "rnd"))
    assert titles == ["Dune", "Dune Messiah", "Ubik"], "rnd should list entities, here all three"


def test_stats_counts_each_storage(library):
    assert lines(FakeKind, library, "stats") == [
        "» 3 notes",
        "» shelf: 3 | reachable · updated just now",
        "» satchel: 1 | reachable · updated just now",
        f"» hoard {__version__} | schema v{len(_db.MIGRATIONS)}",
    ], "stats should count entities and each storage's copies"


@pytest.mark.parametrize(
    "labels, first",
    [({}, "» 3 items"), ({"one": "note", "many": "notes"}, "» 3 notes")],
)
def test_stats_counts_in_the_kinds_own_nouns(library, labels, first):
    kind = FakeKind._replace(labels=labels)
    assert lines(kind, library, "stats")[0] == first, "the kind's labels should name what is counted"
