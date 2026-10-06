from __future__ import annotations

import pytest

from hoard import _index, _search, api
from hoard.contract import Command
from hoard.render import text
from hoard.testing import FakeKind
from hoard.testing.fake import write_note

UNCOVERED = {"Dune", "Dune Messiah"}

COVERED = FakeKind._replace(
    icon=lambda entity: None if entity.title in UNCOVERED else f"/covers/{entity.id}.png",
    commands={"loose": Command("Pack", "pack", off=("satchel",))},
)


def notes(shelf):
    write_note(shelf, "dune", "Dune", "Frank Herbert", "1965", mtime=4000)
    write_note(shelf, "messiah", "Dune Messiah", "Frank Herbert", "1969", mtime=3000)
    write_note(shelf, "children", "Children of Dune", "Frank Herbert", "1976", mtime=2000)
    write_note(shelf, "ubik", "Ubik", "Philip K. Dick", "1969", mtime=1000)


@pytest.fixture
def library(ctx, shelf):
    notes(shelf)
    api.update(COVERED, ctx)
    return ctx


def titles(ctx, typed):
    return [line.split(" | ")[0] for line in text.render(api.filter(COVERED, typed, ctx)) if not line.startswith("»")]


@pytest.mark.parametrize(
    "typed, expected",
    [
        ("", ["Children of Dune", "Ubik", "Dune", "Dune Messiah"]),
        ("dune", ["Children of Dune", "Dune", "Dune Messiah"]),
        ("herbert", ["Children of Dune", "Dune", "Dune Messiah"]),
        ("loose", ["Children of Dune", "Ubik", "Dune", "Dune Messiah"]),
    ],
)
def test_books_with_a_cover_come_before_books_without(library, typed, expected):
    assert titles(library, typed) == expected, f"{typed!r} should list covered books first, each group newest first"


def test_the_limit_keeps_covered_books_before_newer_uncovered_ones(tmp_db, ctx, shelf):
    notes(shelf)
    _index.update(tmp_db, COVERED, ctx)
    assert [row[1] for row in _search.search(tmp_db, "", limit=2)] == ["Children of Dune", "Ubik"], (
        "the limit should cut after ordering by cover, so a newer uncovered book cannot push covered ones out"
    )


def test_a_batch_runs_in_the_same_order_as_the_rows(tmp_db, ctx, shelf):
    notes(shelf)
    _index.update(tmp_db, COVERED, ctx)
    titles_by_id = dict(tmp_db.execute("SELECT id, title FROM entities"))
    assert [titles_by_id[i] for i in _search.ids(tmp_db, "")] == ["Children of Dune", "Ubik", "Dune", "Dune Messiah"], (
        "batch ids should follow the order the rows are shown in"
    )
