from __future__ import annotations

import pytest

from hoard import _fold, api
from hoard.contract import Suggestion
from hoard.testing import FakeKind
from hoard.testing.fake import write_note


def titles_into(log):
    return lambda founds, ctx: log.append(sorted(found.entity.title for found in founds))


@pytest.fixture
def two_notes(ctx, shelf):
    write_note(shelf, "dune", "Dune", "Frank Herbert", "1965")
    write_note(shelf, "ubik", "Ubik", "Philip K. Dick", "1969")
    return ctx


def test_the_kind_is_told_what_every_update_found(two_notes, shelf):
    seen = []
    kind = FakeKind._replace(updated=titles_into(seen))
    api.update(kind, two_notes)
    write_note(shelf, "eyre", "Jane Eyre")
    api.update(kind, two_notes)
    assert seen == [["Dune", "Ubik"], ["Dune", "Jane Eyre", "Ubik"]], "each update should hand the kind everything it found"


def test_the_kind_is_told_after_a_verb_changed_the_storages(two_notes):
    seen = []
    kind = FakeKind._replace(updated=lambda founds, ctx: seen.append(sorted(found.places for found in founds)))
    api.update(kind, two_notes)
    api.act(kind, "pack", ["batch:loose"], two_notes)
    assert seen[-1] == ["shelf +satchel", "shelf +satchel"], "the update after a verb should tell the kind where things are now"


def test_the_kind_is_told_with_the_storages_looked_at(two_notes):
    asleep = []
    sleepy = tuple(storage._replace(sleeps=True) for storage in FakeKind.storages)
    kind = FakeKind._replace(storages=sleepy, updated=lambda founds, ctx: asleep.append(dict(ctx.asleep)))
    api.update(kind, two_notes)
    api.update(kind, two_notes)
    assert asleep == [{}, {}], "an update reads the storages, so the kind should get a context that takes nothing on trust"


def test_the_kind_is_told_before_it_is_asked_for_suggestions(two_notes):
    order = []
    kind = FakeKind._replace(
        updated=lambda founds, ctx: order.append("updated"),
        suggest=lambda founds, ctx: order.append("suggest") or [Suggestion(founds[0].entity.id, "scifi", 0.8)],
    )
    api.update(kind, two_notes)
    assert order == ["updated", "suggest"], "what the kind notes at an update should be there when it suggests"


def test_a_kind_that_fails_to_take_note_does_not_stop_the_update(two_notes, capsys):
    def forgetful(founds, ctx):
        raise OSError("disk full")

    kind = FakeKind._replace(updated=forgetful)
    assert api.update(kind, two_notes) == 2, "the update should finish whatever the kind's hook does"
    assert "updated: OSError('disk full')" in capsys.readouterr().err, "the failure should be logged for worker.log"


@pytest.mark.parametrize(
    "hooks, folds",
    [
        ({}, 0),
        ({"updated": titles_into([])}, 1),
        ({"suggest": lambda founds, ctx: []}, 1),
        ({"updated": titles_into([]), "suggest": lambda founds, ctx: []}, 1),
    ],
)
def test_every_entity_is_folded_once_for_the_hooks_that_want_it(two_notes, mocker, hooks, folds):
    fold = mocker.spy(_fold, "fold")
    assert api.update(FakeKind._replace(**hooks), two_notes) == 2, "the update should still read both notes"
    assert fold.call_count == folds, f"{sorted(hooks) or 'no hooks'} should cost {folds} fold of everything"
