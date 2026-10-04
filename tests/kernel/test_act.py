from __future__ import annotations

import pytest

from hoard import api
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
