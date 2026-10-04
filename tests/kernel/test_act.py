from __future__ import annotations

import os
from pathlib import Path

import pytest

from hoard import api
from hoard.render import text
from hoard.testing import FakeKind
from hoard.testing.fake import read_note, write_note


@pytest.fixture
def dune(ctx, shelf):
    path = write_note(shelf, "dune", "Dune", "Frank Herbert", "1965")
    api.update(FakeKind, ctx)
    return read_note(path).id, path


@pytest.mark.parametrize(
    "verb, command, message",
    [
        ("open", ["open"], "Opened Dune"),
        ("reveal", ["open", "-R"], "Revealed Dune"),
    ],
)
def test_kernel_verbs_hand_the_locator_to_the_system(ctx, dune, mocker, verb, command, message):
    run = mocker.patch("subprocess.run")
    entity_id, path = dune
    assert api.act(FakeKind, verb, [entity_id], ctx) == message, f"{verb} should report what it did"
    run.assert_called_once_with([*command, path], check=False)


def test_open_names_how_many_when_several(ctx, shelf, mocker):
    mocker.patch("subprocess.run")
    ids = [read_note(write_note(shelf, name, name.title())).id for name in ("dune", "ubik")]
    api.update(FakeKind, ctx)
    assert api.act(FakeKind, "open", ids, ctx) == "Opened 2 items", "several targets should be counted"


def test_an_unknown_id_opens_nothing(ctx, dune, mocker):
    run = mocker.patch("subprocess.run")
    assert api.act(FakeKind, "open", ["missing"], ctx) == "Nothing to open", "unknown ids should be reported"
    run.assert_not_called()


def test_an_unknown_verb_is_reported(ctx, dune):
    assert api.act(FakeKind, "juggle", [dune[0]], ctx) == "No verb juggle", "an unknown verb should not crash"


def tree_bytes(*roots):
    return {
        os.path.relpath(os.path.join(folder, name), str(root)): Path(folder, name).read_bytes()
        for root in roots
        for folder, _, names in os.walk(str(root))
        for name in names
    }


@pytest.fixture
def two_notes(ctx, shelf):
    ids = [read_note(write_note(shelf, name, name.title())).id for name in ("dune", "ubik")]
    api.update(FakeKind, ctx)
    return ids


def first_line(ctx, typed):
    return text.render(api.filter(FakeKind, typed, ctx))[0]


@pytest.mark.parametrize(
    "count, message",
    [(1, "Pack into the satchel: Dune"), (2, "Pack into the satchel: 2 items")],
)
def test_a_kind_verb_reports_what_changed(ctx, two_notes, count, message):
    assert api.act(FakeKind, "pack", two_notes[:count], ctx) == message, "the notification should name the result"


def test_a_kind_verb_refreshes_the_index(ctx, two_notes):
    api.act(FakeKind, "pack", two_notes[:1], ctx)
    assert first_line(ctx, "dune").startswith("Dune | shelf +satchel · "), "the copy should show at once"


def test_a_verb_that_changes_nothing_says_so_and_records_nothing(ctx, two_notes):
    api.act(FakeKind, "pack", two_notes[:1], ctx)
    assert api.act(FakeKind, "pack", two_notes[:1], ctx) == "Pack into the satchel: nothing to do", (
        "a verb with no changes should say so"
    )
    api.act(FakeKind, "undo", [], ctx)
    assert api.act(FakeKind, "undo", [], ctx) == "Nothing to undo", "an empty run should not leave a batch"


def test_undo_restores_the_tree_to_the_byte(ctx, two_notes, shelf, satchel):
    before = tree_bytes(shelf, satchel)
    api.act(FakeKind, "pack", two_notes, ctx)
    assert api.act(FakeKind, "undo", [], ctx) == "Undid Pack into the satchel", "undo should name what it undid"
    assert tree_bytes(shelf, satchel) == before, "undo should leave both storages exactly as they were"
    assert first_line(ctx, "dune").startswith("Dune | shelf · "), "undo should refresh the index too"


def test_a_verb_without_undo_is_flagged_and_skipped_by_undo(ctx, two_notes, satchel):
    api.act(FakeKind, "pack", two_notes[:1], ctx)
    assert api.act(FakeKind, "toss", two_notes, ctx) == "Toss: 2 items (cannot be undone)", "say it is final"
    assert api.act(FakeKind, "undo", [], ctx) == "Undid Pack into the satchel", "undo should reach past toss"
    assert os.listdir(satchel) == [], "the earlier undoable batch should be the one undone"


def test_nothing_to_undo(ctx):
    assert api.act(FakeKind, "undo", [], ctx) == "Nothing to undo", "an empty journal should say so"
