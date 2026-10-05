from __future__ import annotations

import os

import pytest

from hoard import _plan, api
from hoard.contract import Step
from hoard.testing import FakeKind
from hoard.testing.fake import write_note


@pytest.fixture
def outside(tmp_path):
    folder = tmp_path / "outside"
    folder.mkdir()
    return folder


@pytest.fixture
def escape(shelf, outside):
    (shelf / "escape").symlink_to(outside, target_is_directory=True)
    return shelf / "escape"


@pytest.fixture
def kernel_ctx(ctx):
    return api.context(FakeKind, ctx)


@pytest.mark.parametrize(
    "target",
    ["../outside/Dune.note", "sub/../../outside/Dune.note", "escape/Dune.note", "escape/../../outside/Dune.note"],
)
def test_a_move_never_lands_outside_its_root(kernel_ctx, shelf, outside, escape, target):
    path = write_note(shelf, "dune", "Dune")
    step = Step("move", "id", path, os.path.join(str(shelf), target), "canonical name")
    assert _plan.apply_step(step, kernel_ctx) is None, f"a move to {target} resolves outside the root and should be skipped"
    assert os.path.exists(path), "the file should stay where it was"
    assert os.listdir(outside) == [], "nothing should arrive outside the root"


@pytest.mark.parametrize("before", ["../outside/victim.tmp", "escape/victim.tmp"])
def test_a_step_never_takes_a_file_from_outside_its_root(kernel_ctx, shelf, outside, escape, before):
    victim = outside / "victim.tmp"
    victim.write_bytes(b"keep me")
    step = Step("trash", "", os.path.join(str(shelf), before), None, "junk")
    assert _plan.apply_step(step, kernel_ctx) is None, f"{before} resolves outside the root and should be skipped"
    assert victim.read_bytes() == b"keep me", "a file outside the root should stay put"


@pytest.mark.parametrize("name", ["..", "."])
def test_a_target_naming_a_folder_reference_is_skipped(kernel_ctx, shelf, name):
    path = write_note(shelf, "dune", "Dune")
    step = Step("move", "id", path, os.path.join(str(shelf), "sub", name), "canonical name")
    assert _plan.apply_step(step, kernel_ctx) is None, f"a target ending in {name!r} names no file and should be skipped"
    assert os.path.exists(path), "the file should stay where it was"


def test_a_move_inside_a_symlinked_root_still_works(tmp_path, context_with):
    real = tmp_path / "real-shelf"
    real.mkdir()
    (tmp_path / "linked-shelf").symlink_to(real, target_is_directory=True)
    linked = tmp_path / "linked-shelf"
    ctx = api.context(FakeKind, context_with(fake_shelf=str(linked), fake_satchel=str(tmp_path / "satchel")))
    path = write_note(linked, "dune", "Dune")
    change = _plan.apply_step(Step("move", "id", path, str(linked / "Dune.note"), "canonical name"), ctx)
    assert change is not None, "a root reached through a symlink is still the root"
    assert (real / "Dune.note").exists(), "the move should happen inside the real folder"


def test_one_failing_step_keeps_the_others_undoable(ctx, shelf, mocker):
    good = write_note(shelf, "dune", "Dune")
    bad = write_note(shelf, "ubik", "Ubik")
    api.update(FakeKind, ctx)
    real_rename = os.rename

    def rename(source, target):
        if source == bad:
            raise OSError(18, "Invalid cross-device link")
        real_rename(source, target)

    mocker.patch("hoard._plan.os.rename", side_effect=rename)
    steps = [
        _plan.encode(Step("move", "a", good, str(shelf / "Dune.note"), "canonical name")),
        _plan.encode(Step("move", "b", bad, str(shelf / "Ubik.note"), "canonical name")),
    ]
    assert api.act(FakeKind, "apply", steps, ctx) == "Fixed Dune.note · 1 skipped", "a step that fails should be skipped and counted"
    mocker.stopall()
    assert api.act(FakeKind, "undo", [], ctx) == "Undid Fix", "the steps that ran should still be in the journal"
    assert os.path.exists(good), "undo should bring back the step that ran before the failure"


def test_undo_never_overwrites_a_file_that_took_the_old_place(kernel_ctx, shelf):
    path = write_note(shelf, "dune", "Dune")
    change = _plan.apply_step(Step("move", "id", path, str(shelf / "Dune.note"), "canonical name"), kernel_ctx)
    (shelf / "dune.note").write_text("downloaded again")
    _plan.undo_changes([change], kernel_ctx)
    assert (shelf / "dune.note").read_text() == "downloaded again", "undo should not overwrite a file that arrived since"
    assert (shelf / "Dune.note").exists(), "the moved file should stay where the step put it"


def test_undo_goes_on_after_a_change_it_cannot_restore(kernel_ctx, shelf):
    first = write_note(shelf, "dune", "Dune")
    second = write_note(shelf, "ubik", "Ubik")
    changes = [
        _plan.apply_step(Step("move", "a", first, str(shelf / "Dune.note"), "canonical name"), kernel_ctx),
        _plan.apply_step(Step("move", "b", second, str(shelf / "Ubik.note"), "canonical name"), kernel_ctx),
    ]
    os.remove(shelf / "Ubik.note")
    _plan.undo_changes(changes, kernel_ctx)
    assert os.path.exists(first), "a missing file in one change should not stop the others from coming back"
