from __future__ import annotations

import os
from pathlib import Path

import pytest

from hoard import _plan, api, cli
from hoard.contract import Context, Step
from hoard.render import text
from hoard.testing import FakeKind
from hoard.testing.fake import write_note


def tree(*roots):
    return {
        (str(root), str(path.relative_to(root))): path.read_bytes()
        for root in roots
        for path in sorted(Path(root).rglob("*"))
        if path.is_file()
    }


@pytest.fixture
def messy(ctx, shelf):
    write_note(shelf, "dune", "Dune", mtime=3000)
    write_note(shelf, "Ubik", "Ubik", mtime=2000)
    (shelf / "download.tmp").write_bytes(b"half a file")
    api.update(FakeKind, ctx)
    return ctx


def lines(ctx, typed="fix"):
    return text.render(api.filter(FakeKind, typed, ctx))


def test_fix_lists_the_kinds_plan_under_an_apply_row(messy):
    assert lines(messy) == [
        "» Apply 2 | ↩ runs every step below",
        "Dune.note | canonical name · from dune.note",
        "download.tmp | junk · to the trash",
    ], "fix should show one row per step, after one row that applies them all"


def test_fix_words_narrow_the_plan_to_matching_entities(messy):
    assert lines(messy, "fix dune")[1:] == ["Dune.note | canonical name · from dune.note"], (
        "words after fix should lint only matching entities; junk has no entity and needs no words"
    )


def test_a_kind_without_lint_has_nothing_to_fix(ctx, shelf):
    write_note(shelf, "dune", "Dune")
    kind = FakeKind._replace(lint=None)
    api.update(kind, ctx)
    assert text.render(api.filter(kind, "fix", ctx)) == ["» Nothing to fix"], "no lint means nothing to fix"


def test_a_clean_tree_has_nothing_to_fix(ctx, shelf):
    write_note(shelf, "Dune", "Dune")
    api.update(FakeKind, ctx)
    assert lines(ctx) == ["» Nothing to fix"], "a tree that already follows the plan should say so"


def test_applying_the_plan_then_undoing_restores_the_tree_to_the_byte(messy, shelf, satchel):
    before = tree(shelf, satchel)
    assert api.act(FakeKind, "apply", ["plan:"], messy) == "Fixed 2 items", "apply should count what it did"
    assert sorted(os.listdir(shelf)) == [".hoard-trash", "Dune.note", "Ubik.note"], "the plan should be carried out"
    assert lines(messy) == ["» Nothing to fix"], "after applying, the plan should be empty"
    assert api.act(FakeKind, "undo", [], messy) == "Undid Fix", "the whole plan should undo as one batch"
    assert tree(shelf, satchel) == before, "undo should restore every byte and name"
    assert not (shelf / ".hoard-trash").exists(), "undo should not leave an empty trash folder behind"


def test_a_single_step_row_applies_only_itself(messy, shelf):
    step_row = api.filter(FakeKind, "fix", messy).rows[1]
    assert api.act(FakeKind, "apply", [step_row.id], messy) == "Fixed Dune.note", "one row should apply one step"
    assert (shelf / "download.tmp").exists(), "other steps should wait"


def test_a_step_that_would_overwrite_is_skipped(ctx, shelf):
    write_note(shelf, "draft", "Dune")
    (shelf / "Dune.note").write_text("another note")
    (shelf / "download.tmp").write_bytes(b"half a file")
    api.update(FakeKind, ctx)
    assert lines(ctx)[1] == "Dune.note | canonical name · from draft.note", "the plan proposes it"
    assert api.act(FakeKind, "apply", ["plan:"], ctx) == "Fixed download.tmp · 1 skipped", (
        "a move onto a different existing file should be skipped and counted"
    )
    assert (shelf / "Dune.note").read_text() == "another note", "nothing should be overwritten"


def test_the_trash_keeps_the_relative_path_and_never_overwrites(ctx, shelf):
    (shelf / "deep").mkdir()
    (shelf / "deep" / "a.tmp").write_bytes(b"one")
    root = str(shelf)
    first = _plan.trash_path(str(shelf / "deep" / "a.tmp"), root)
    assert first == os.path.join(root, ".hoard-trash", "deep", "a.tmp"), "the trash mirrors the storage"
    os.makedirs(os.path.dirname(first))
    Path(first).write_bytes(b"older")
    assert _plan.trash_path(str(shelf / "deep" / "a.tmp"), root) == os.path.join(root, ".hoard-trash", "deep", "a (2).tmp"), (
        "a second trashing of the same name should not overwrite the first"
    )


@pytest.mark.parametrize(
    "step",
    [
        Step("move", "id1", "/shelf/a b.note", "/shelf/Á b.note", "canonical name"),
        Step("trash", "", "/shelf/x.tmp", None, "junk"),
    ],
)
def test_steps_round_trip_through_a_row_argument(step):
    assert _plan.decode(_plan.encode(step)) == step, "a row should carry its step exactly"


def test_a_path_outside_every_storage_is_never_touched(ctx, tmp_path):
    outside = tmp_path / "elsewhere.tmp"
    outside.write_bytes(b"x")
    ctx = api.context(FakeKind, ctx)
    assert _plan.apply_step(Step("trash", "", str(outside), None, "junk"), ctx) is None, "only storage files move"
    assert outside.exists(), "a file outside the storages should stay put"


def test_unknown_step_verbs_are_skipped(ctx, shelf):
    path = write_note(shelf, "dune", "Dune")
    ctx = api.context(FakeKind, ctx)
    assert _plan.apply_step(Step("shred", "id", path, None, "?"), ctx) is None, "only move and trash are known"


def test_the_cli_prints_the_plan_without_applying_it(messy, shelf, capsys, monkeypatch):
    monkeypatch.setenv("alfred_workflow_data", messy.data)
    monkeypatch.setenv("alfred_workflow_cache", messy.cache)
    for name, value in messy.config.items():
        monkeypatch.setenv(name, value)
    cli.main("hoard.testing.fake", ["plan"])
    assert capsys.readouterr().out.splitlines() == [
        f"move   {shelf}/dune.note → {shelf}/Dune.note  (canonical name)",
        f"trash  {shelf}/download.tmp  (junk)",
    ], "plan should print every step and change nothing"
    assert (shelf / "dune.note").exists(), "a dry run should not move anything"


def test_a_target_that_is_the_same_file_is_not_a_conflict(tmp_path):
    original = tmp_path / "dune.note"
    original.write_text("x")
    os.link(original, tmp_path / "alias.note")
    assert not _plan.blocked(str(original), str(tmp_path / "alias.note")), (
        "a target that is the same file, as a case-only rename is on macOS, must not block the move"
    )


def test_context_roots_decide_where_a_path_belongs(tmp_path):
    ctx = Context(data="", cache="", roots={"shelf": (str(tmp_path / "shelf"),)})
    assert _plan.root_of(str(tmp_path / "shelf" / "a" / "b"), ctx) == str(tmp_path / "shelf"), "inside a root"
    assert _plan.root_of(str(tmp_path / "shelfish" / "b"), ctx) is None, "a sibling with a shared prefix is outside"


def test_a_folder_moves_and_undoes_like_a_file(ctx, shelf):
    (shelf / "dune.sdr").mkdir()
    (shelf / "dune.sdr" / "metadata.lua").write_text("progress")
    ctx = api.context(FakeKind, ctx)
    change = _plan.apply_step(Step("move", "id", str(shelf / "dune.sdr"), str(shelf / "Dune.sdr"), "sidecar"), ctx)
    assert (shelf / "Dune.sdr" / "metadata.lua").read_text() == "progress", "a folder should move whole"
    _plan.undo_changes([change], ctx)
    assert (shelf / "dune.sdr" / "metadata.lua").read_text() == "progress", "and come back whole"


def test_a_folder_emptied_by_a_step_goes_and_comes_back_with_undo(ctx, shelf):
    (shelf / "copies").mkdir()
    (shelf / "copies" / "a.tmp").write_bytes(b"x")
    ctx = api.context(FakeKind, ctx)
    change = _plan.apply_step(Step("trash", "", str(shelf / "copies" / "a.tmp"), None, "junk"), ctx)
    assert not (shelf / "copies").exists(), "a folder left empty by a step should be removed"
    _plan.undo_changes([change], ctx)
    assert (shelf / "copies" / "a.tmp").read_bytes() == b"x", "undo should recreate the folder and the file"
