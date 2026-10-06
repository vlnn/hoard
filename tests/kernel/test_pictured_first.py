from __future__ import annotations

import pytest

from hoard import _index, _search, api
from hoard.render import text
from hoard.testing import FakeKind
from hoard.testing.fake import write_note

UNPICTURED = {"Dune", "Dune Messiah"}


def picture(entity):
    return None if entity.title in UNPICTURED else f"/covers/{entity.id}.png"


PICTURED = FakeKind._replace(icon=picture)
PICTURED_FIRST = PICTURED._replace(pictured_first=True)


def notes(shelf):
    write_note(shelf, "dune", "Dune", "Frank Herbert", "1965", mtime=4000)
    write_note(shelf, "messiah", "Dune Messiah", "Frank Herbert", "1969", mtime=3000)
    write_note(shelf, "children", "Children of Dune", "Frank Herbert", "1976", mtime=2000)
    write_note(shelf, "ubik", "Ubik", "Philip K. Dick", "1969", mtime=1000)


@pytest.fixture
def library(ctx, shelf):
    notes(shelf)
    api.update(PICTURED_FIRST, ctx)
    return ctx


def titles(kind, ctx, typed):
    return [line.split(" | ")[0] for line in text.render(api.filter(kind, typed, ctx)) if not line.startswith("»")]


@pytest.mark.parametrize(
    "typed, expected",
    [
        ("", ["Children of Dune", "Ubik", "Dune", "Dune Messiah"]),
        ("dune", ["Children of Dune", "Dune", "Dune Messiah"]),
        ("herbert", ["Children of Dune", "Dune", "Dune Messiah"]),
        ("loose", ["Children of Dune", "Ubik", "Dune", "Dune Messiah"]),
    ],
)
def test_a_pictured_first_kind_lists_entities_with_a_picture_first(library, typed, expected):
    assert titles(PICTURED_FIRST, library, typed) == expected, f"{typed!r} should list pictured entities first, each group newest first"


@pytest.mark.parametrize("typed", ["", "loose"])
def test_a_kind_lists_newest_first_unless_it_asks_otherwise(library, typed):
    assert titles(PICTURED, library, typed) == ["Dune", "Dune Messiah", "Children of Dune", "Ubik"], (
        f"{typed!r} should stay newest first for a kind that does not set pictured_first"
    )


def test_the_limit_keeps_pictured_entities_before_newer_unpictured_ones(tmp_db, ctx, shelf):
    notes(shelf)
    _index.update(tmp_db, PICTURED_FIRST, ctx)
    assert [row[1] for row in _search.search(tmp_db, "", limit=2, order=_search.PICTURED_FIRST)] == ["Children of Dune", "Ubik"], (
        "the limit should cut after ordering by picture, so a newer unpictured entity cannot push pictured ones out"
    )


def test_a_batch_runs_in_the_same_order_as_the_rows(tmp_db, ctx, shelf):
    notes(shelf)
    _index.update(tmp_db, PICTURED_FIRST, ctx)
    titles_by_id = dict(tmp_db.execute("SELECT id, title FROM entities"))
    assert [titles_by_id[i] for i in _search.ids(tmp_db, "", order=_search.PICTURED_FIRST)] == ["Children of Dune", "Ubik", "Dune", "Dune Messiah"], (
        "batch ids should follow the order the rows are shown in"
    )
