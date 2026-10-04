from __future__ import annotations

import os

import pytest

from hoard import api
from hoard.items import Mod
from hoard.render import text
from hoard.testing import FakeKind
from hoard.testing.fake import write_note

SATCHEL_FIRST = FakeKind._replace(storages=tuple(reversed(FakeKind.storages)))


@pytest.fixture
def dune_twice(ctx, shelf, satchel):
    shelf_copy = write_note(shelf, "dune", "Dune", "Frank Herbert", "1965")
    satchel_copy = write_note(satchel, "dune", "Dune", "Frank Herbert", "1965")
    api.update(FakeKind, ctx)
    return shelf_copy, satchel_copy


def only_row(kind, ctx, typed="dune"):
    (item,) = api.filter(kind, typed, ctx).rows
    return item


@pytest.mark.parametrize(
    "kind, place, copy",
    [
        (FakeKind, "shelf +satchel", 0),
        (SATCHEL_FIRST, "satchel +shelf", 1),
    ],
)
def test_one_entity_in_two_storages_is_one_row_at_the_kinds_first_storage(ctx, dune_twice, kind, place, copy):
    item = only_row(kind, ctx)
    assert item.subtitle.startswith(f"{place} · "), "the subtitle should name every place, nearest first"
    assert item.locator == dune_twice[copy], "the row should point at the copy in the kind's first storage"


def test_an_unreachable_storage_hands_the_row_to_the_next(ctx, dune_twice, shelf, tmp_path):
    os.rename(shelf, tmp_path / "unplugged")
    item = only_row(FakeKind, ctx)
    assert (item.subtitle.split(" · ")[0], item.locator) == ("satchel +shelf", dune_twice[1]), (
        "when the first storage is unplugged the row should show the reachable copy"
    )


def test_a_row_with_no_reachable_copy_says_so_and_offers_no_modifiers(ctx, dune_twice, shelf, satchel, tmp_path):
    os.rename(shelf, tmp_path / "unplugged shelf")
    os.rename(satchel, tmp_path / "unplugged satchel")
    item = only_row(FakeKind, ctx)
    assert item.subtitle.startswith("shelf +satchel (not reachable) · "), "an unreachable row should say so"
    assert item.mods == (), "nothing can be opened or revealed when no copy is reachable"


def test_reachable_rows_offer_open_and_reveal(ctx, dune_twice):
    assert only_row(FakeKind, ctx).mods == (
        Mod("shift", "open", "Open"),
        Mod("alt", "reveal", "Reveal in Finder"),
    ), "⇧↩ should open and ⌥↩ should reveal"


def test_default_verb_sees_every_place(ctx, shelf, satchel):
    write_note(shelf, "dune", "Dune")
    write_note(shelf, "ubik", "Ubik")
    write_note(satchel, "ubik", "Ubik")
    kind = FakeKind._replace(default_verb=lambda found: "open" if found.on("satchel") else "pack")
    api.update(kind, ctx)
    verbs = {item.title: item.verb for item in api.filter(kind, "", ctx).rows}
    assert verbs == {"Dune": "pack", "Ubik": "open"}, "↩ should follow what the kind decides from the sightings"


def test_a_single_storage_kind_shows_no_places(ctx, shelf):
    write_note(shelf, "dune", "Dune", "Frank Herbert", "1965")
    kind = FakeKind._replace(storages=FakeKind.storages[:1])
    api.update(kind, ctx)
    assert text.render(api.filter(kind, "dune", ctx)) == [f"Dune | Frank Herbert · 1965 · {shelf}/dune.note"], (
        "with one storage there is no place to name"
    )


@pytest.mark.parametrize(
    "make_shelf, setting, expected",
    [
        (False, "shelf", "» Not reachable: {shelf} | shelf · is the drive connected?"),
        (True, "", "» No folder set for shelf | set fake_shelf in the workflow configuration"),
    ],
)
def test_an_empty_index_explains_missing_folders(context_with, shelf, satchel, make_shelf, setting, expected):
    satchel.mkdir()
    if make_shelf:
        shelf.mkdir()
    config = {"fake_shelf": str(shelf)} if setting else {}
    lines = text.render(api.filter(FakeKind, "", context_with(fake_satchel=str(satchel), **config)))
    assert lines == [expected.format(shelf=shelf), "» Index is empty | ↩ to update the index"], (
        "an empty index should say which folder is missing before offering to update"
    )
