from __future__ import annotations

import os

import pytest

from hoard import api
from hoard.contract import Verb
from hoard.render import text
from hoard.testing import FakeKind
from hoard.testing.fake import write_note

SLEEPY = FakeKind._replace(storages=tuple(storage._replace(sleeps=True) for storage in FakeKind.storages))


@pytest.fixture
def dune_twice(ctx, shelf, satchel):
    copies = [write_note(root, "dune", "Dune", "Frank Herbert", "1965") for root in (shelf, satchel)]
    api.update(SLEEPY, ctx)
    return copies


def unplug(root, tmp_path) -> None:
    os.rename(root, tmp_path / f"unplugged {root.name}")


def plug_in(root, tmp_path) -> None:
    os.rename(tmp_path / f"unplugged {root.name}", root)


def place_and_locator(kind, ctx, typed="dune") -> tuple:
    (item,) = api.filter(kind, typed, ctx).rows
    return item.subtitle.split(" · ")[0], item.locator


def spy(mocker, asked):
    watching = mocker.Mock(side_effect=asked)
    watching.setting = getattr(asked, "setting", "")
    return watching


def watched(kind, mocker):
    storages = tuple(s._replace(roots=spy(mocker, s.roots), mounted=spy(mocker, s.mounted)) for s in kind.storages)
    return kind._replace(storages=storages), storages


def times_asked(storages) -> int:
    return sum(storage.roots.call_count + storage.mounted.call_count for storage in storages)


def test_a_storage_is_looked_at_on_every_keystroke_unless_it_says_it_sleeps():
    assert not any(storage.sleeps for storage in FakeKind.storages), "sleeping should be something a storage asks for"


def test_a_sleeping_storage_is_listed_as_the_last_update_found_it(ctx, dune_twice, shelf, tmp_path):
    unplug(shelf, tmp_path)
    assert place_and_locator(SLEEPY, ctx) == ("shelf +satchel", dune_twice[0]), (
        "between updates a sleeping storage should be taken as the update found it"
    )


@pytest.mark.parametrize("typed", ["", "dune", "du", "loose", "stats", "tag", "like", "undo"])
def test_a_keystroke_asks_a_sleeping_storage_nothing(ctx, dune_twice, mocker, typed):
    kind, storages = watched(SLEEPY, mocker)
    api.filter(kind, typed, ctx)
    assert times_asked(storages) == 0, f"typing {typed!r} should ask a sleeping storage neither where it is nor whether it is there"


def test_an_empty_index_asks_a_sleeping_storage_nothing_either(ctx, mocker):
    api.update(SLEEPY, ctx)
    kind, storages = watched(SLEEPY, mocker)
    assert text.render(api.filter(kind, "", ctx)) == ["» Index is empty | ↩ to update the index"], "nothing is missing, nothing is indexed"
    assert times_asked(storages) == 0, "folders the update reached should not be looked for again while the index is empty"


def test_a_waking_storage_is_asked_on_every_keystroke(ctx, dune_twice, mocker):
    kind, storages = watched(FakeKind, mocker)
    api.filter(kind, "dune", ctx)
    assert all(s.roots.call_count and s.mounted.call_count for s in storages), (
        "a storage that does not sleep should be asked where and whether it is, as before"
    )


def test_the_next_update_notices_an_unplugged_sleeping_storage(ctx, dune_twice, shelf, tmp_path):
    unplug(shelf, tmp_path)
    api.update(SLEEPY, ctx)
    assert place_and_locator(SLEEPY, ctx) == ("satchel +shelf", dune_twice[1]), (
        "an update should see that the storage is gone and hand the row to the next copy"
    )


def test_a_sleeping_storage_found_missing_is_looked_for_again(ctx, dune_twice, shelf, tmp_path):
    unplug(shelf, tmp_path)
    api.update(SLEEPY, ctx)
    plug_in(shelf, tmp_path)
    assert place_and_locator(SLEEPY, ctx) == ("shelf +satchel", dune_twice[0]), (
        "a storage the update did not reach should be looked for on each keystroke, so plugging it in shows at once"
    )


def test_a_storage_with_one_folder_missing_is_not_taken_on_trust(context_with, shelf, satchel, tmp_path):
    attic = tmp_path / "attic"
    for root in (shelf, satchel, attic):
        root.mkdir()
    ctx = context_with(fake_shelf=f"{shelf}\n{attic}", fake_satchel=str(satchel))
    write_note(attic, "dune", "Dune")
    unplug(shelf, tmp_path)
    api.update(SLEEPY, ctx)
    unplug(attic, tmp_path)
    assert place_and_locator(SLEEPY, ctx)[0] == "shelf (not reachable)", (
        "a storage only partly reachable at the update should be looked at whole on a keystroke"
    )


def test_an_index_from_before_sleeping_storages_is_looked_at(ctx, dune_twice, shelf, tmp_path):
    con = api.open_database(SLEEPY, ctx)
    con.execute("UPDATE storage_state SET roots_json = NULL, reach_json = NULL")
    con.commit()
    con.close()
    unplug(shelf, tmp_path)
    assert place_and_locator(SLEEPY, ctx)[0] == "satchel +shelf", "with nothing remembered a keystroke should look, as it always did"


def test_a_sleeping_storage_without_folders_is_left_asleep_too(context_with, satchel, mocker):
    satchel.mkdir()
    ctx = context_with(fake_satchel=str(satchel))
    write_note(satchel, "dune", "Dune")
    api.update(SLEEPY, ctx)
    kind, storages = watched(SLEEPY, mocker)
    assert place_and_locator(kind, ctx)[0] == "satchel", "the one copy should be listed where it is"
    assert times_asked(storages) == 0, "a storage that had no folders at the update has nothing to be asked about until the next"


def test_a_verb_looks_at_a_sleeping_storage(ctx, dune_twice, shelf, tmp_path):
    nearest = []
    peek = Verb("Peek", lambda founds, ctx: nearest.extend(found.nearest.storage for found in founds) or [])
    kind = SLEEPY._replace(verbs={"peek": peek})
    (item,) = api.filter(kind, "dune", ctx).rows
    unplug(shelf, tmp_path)
    api.act(kind, "peek", [item.id], ctx)
    assert nearest == ["satchel"], "a verb acts on the disk, so it should see which copy is reachable now"


def test_a_missing_sleeping_storage_is_still_reported_on_an_empty_index(context_with, shelf, satchel):
    satchel.mkdir()
    ctx = context_with(fake_shelf=str(shelf), fake_satchel=str(satchel))
    api.update(SLEEPY, ctx)
    assert text.render(api.filter(SLEEPY, "", ctx))[0] == f"» Not reachable: {shelf} | shelf · is the drive connected?", (
        "a sleeping storage that was not there at the update should be reported like any other"
    )


def test_a_context_that_left_storages_asleep_looks_again_for_a_verb_or_an_update(ctx, dune_twice):
    handed = []
    kind = SLEEPY._replace(subtitle=lambda found, ctx: handed.append(ctx) or "")
    api.filter(kind, "dune", ctx)
    assert set(handed[0].asleep) == {"shelf", "satchel"}, "the keystroke should have left both storages asleep"
    assert api.context(SLEEPY, handed[0]).asleep == {}, "a context resolved for acting should take nothing on trust, wherever it came from"
