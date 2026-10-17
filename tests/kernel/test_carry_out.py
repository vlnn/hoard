from __future__ import annotations

import os
import unicodedata

import pytest

from hoard import _steps, api
from hoard.contract import Change, Step
from hoard.testing import FakeKind
from hoard.testing.fake import write_note


@pytest.fixture
def kernel_ctx(ctx):
    return api.context(FakeKind, ctx)


def names(folder) -> list:
    return sorted(os.listdir(folder))


def test_a_copy_step_copies_a_file_into_another_root(kernel_ctx, shelf, satchel):
    source = write_note(shelf, "dune", "Dune")
    changes = api.carry_out(FakeKind, [Step("copy", "id", source, str(satchel / "Dune.note"), "packed")], kernel_ctx)
    assert changes == [Change("id", "copy", source, str(satchel / "Dune.note"))], "a copy is recorded as such"
    assert (satchel / "Dune.note").read_bytes() == open(source, "rb").read(), "the copy has the source's bytes"
    assert os.path.exists(source), "the source stays"


def test_undoing_a_copy_removes_the_copy_and_the_folder_it_made(kernel_ctx, shelf, satchel):
    source = write_note(shelf, "dune", "Dune")
    changes = api.carry_out(FakeKind, [Step("copy", "id", source, str(satchel / "deep" / "Dune.note"), "packed")], kernel_ctx)
    api.restore(FakeKind, changes, kernel_ctx)
    assert not (satchel / "deep").exists(), "the copy and the folder made for it are gone"
    assert os.path.exists(source), "the source is untouched"


@pytest.mark.parametrize("content", [b"same", b"different"], ids=["same", "different"])
def test_a_copy_onto_an_existing_file_is_skipped(kernel_ctx, shelf, satchel, content):
    source = write_note(shelf, "dune", "Dune")
    target = satchel / "Dune.note"
    target.write_bytes(content)
    assert api.carry_out(FakeKind, [Step("copy", "id", source, str(target), "packed")], kernel_ctx) == [], (
        "copying onto a file that is already there is nothing to do"
    )
    assert target.read_bytes() == content, "the existing file is kept"


def test_a_copy_source_outside_every_root_is_never_read(kernel_ctx, tmp_path, satchel):
    elsewhere = tmp_path / "elsewhere.note"
    elsewhere.write_text("secret")
    assert api.carry_out(FakeKind, [Step("copy", "id", str(elsewhere), str(satchel / "x.note"), "")], kernel_ctx) == [], (
        "a copy, like a move, starts inside a storage root"
    )


def test_a_folder_is_not_copied(kernel_ctx, shelf, satchel):
    (shelf / "sub").mkdir()
    assert api.carry_out(FakeKind, [Step("copy", "id", str(shelf / "sub"), str(satchel / "sub"), "")], kernel_ctx) == [], (
        "copy steps carry files only"
    )


def test_a_move_onto_an_identical_file_removes_the_source_instead(kernel_ctx, shelf):
    source = write_note(shelf, "inbox/dune", "Dune")
    kept = write_note(shelf, "Dune", "Dune")
    changes = api.carry_out(FakeKind, [Step("move", "id", source, kept, "canonical name")], kernel_ctx)
    assert changes == [Change("id", "delete", source, kept)], "a byte-identical source is cleaned up, not skipped"
    assert not (shelf / "inbox").exists(), "the redundant copy and its emptied folder are gone"
    assert os.path.exists(kept), "the kept file is untouched"


def test_undoing_a_delete_brings_the_file_back_from_the_kept_copy(kernel_ctx, shelf):
    source = write_note(shelf, "inbox/dune", "Dune")
    kept = write_note(shelf, "Dune", "Dune")
    changes = api.carry_out(FakeKind, [Step("move", "id", source, kept, "canonical name")], kernel_ctx)
    api.restore(FakeKind, changes, kernel_ctx)
    assert open(source, "rb").read() == open(kept, "rb").read(), "the deleted copy comes back from the kept file"
    api.restore(FakeKind, [Change("id", "move", source, kept)], kernel_ctx)
    assert os.path.exists(kept) and os.path.exists(source), "undo never overwrites a file that is already there"


def test_an_empty_folder_whose_target_exists_is_removed_and_comes_back_with_undo(kernel_ctx, shelf):
    (shelf / "old" / "Empty").mkdir(parents=True)
    (shelf / "new" / "Empty").mkdir(parents=True)
    step = Step("move", "", str(shelf / "old" / "Empty"), str(shelf / "new" / "Empty"), "tidy")
    changes = api.carry_out(FakeKind, [step], kernel_ctx)
    assert changes[0].kind_of_change == "delete" and not (shelf / "old").exists(), (
        "an empty folder already present at its target is simply removed"
    )
    api.restore(FakeKind, changes, kernel_ctx)
    assert (shelf / "old" / "Empty").is_dir(), "the deleted folder is recreated"


def test_a_move_onto_a_different_file_is_skipped(kernel_ctx, shelf):
    source = write_note(shelf, "draft", "Dune")
    (shelf / "Dune.note").write_text("another note")
    assert api.carry_out(FakeKind, [Step("move", "id", source, str(shelf / "Dune.note"), "")], kernel_ctx) == [], (
        "a different file at the destination needs a human"
    )
    assert os.path.exists(source), "the source is left alone"


def test_existing_parent_folders_are_respelled_to_the_steps_case(kernel_ctx, shelf):
    source = write_note(shelf, "Wolfe, Gene/Book of The New Sun/Claw", "Claw")
    target = str(shelf / "Wolfe, Gene" / "Book of the New Sun" / "Claw.note")
    changes = api.carry_out(FakeKind, [Step("move", "id", source, target, "relocate")], kernel_ctx)
    assert changes == [Change("id", "move", source, target)], "a case-only folder rename is a real move"
    assert names(shelf / "Wolfe, Gene") == ["Book of the New Sun"], "the folder now carries the step's spelling"
    assert os.path.exists(target), "the note is under the respelled folder"
    api.restore(FakeKind, changes, kernel_ctx)
    assert names(shelf / "Wolfe, Gene") == ["Book of The New Sun"], "undo respells the folder back"
    assert os.path.exists(source), "and the note is back under it"


def test_a_case_only_rename_keeps_the_file(kernel_ctx, shelf):
    source = write_note(shelf, "БРИНИХ - Шахмати", "Chess")
    target = str(shelf / "Бриних - Шахмати.note")
    assert api.carry_out(FakeKind, [Step("move", "id", source, target, "rename")], kernel_ctx) == [
        Change("id", "move", source, target)
    ], "a case-only file rename is applied"
    assert names(shelf) == ["Бриних - Шахмати.note"], "the file is renamed, not deleted or duplicated"


def test_a_source_spelled_differently_on_disk_is_found(kernel_ctx, shelf):
    nfd = unicodedata.normalize("NFD", "Čapek - Válka")
    write_note(shelf, f"inbox/{nfd}", "Válka")
    before = str(shelf / "inbox" / "Čapek - Válka.note")
    target = str(shelf / "fiction" / "Čapek - Válka.note")
    assert api.carry_out(FakeKind, [Step("move", "id", before, target, "relocate")], kernel_ctx)[0].after == target, (
        "an NFD-named file is found by its NFC step path"
    )
    assert os.path.exists(target), "the note has moved"


def test_a_file_spelled_differently_at_the_destination_counts_as_taken(kernel_ctx, shelf):
    nfd = unicodedata.normalize("NFD", "Čapek - Válka")
    source = write_note(shelf, "inbox/Čapek - Válka", "Válka")
    (shelf / "fiction").mkdir()
    (shelf / "fiction" / f"{nfd}.note").write_text("other")
    target = str(shelf / "fiction" / "Čapek - Válka.note")
    assert api.carry_out(FakeKind, [Step("move", "id", source, target, "relocate")], kernel_ctx) == [], (
        "a differently normalized file at the destination still blocks the move"
    )


def test_the_escort_follows_each_move_as_it_happens_and_each_way_back_on_restore(kernel_ctx, shelf, satchel, mocker):
    escort = mocker.Mock(side_effect=lambda before, after, ctx: escort.seen.append((before, after, os.path.exists(after))))
    escort.seen = []
    kind = FakeKind._replace(escort=escort)
    moved = write_note(shelf, "dune", "Dune")
    copied = write_note(shelf, "ubik", "Ubik")
    (shelf / "junk.tmp").write_bytes(b"x")
    steps = [
        Step("move", "a", moved, str(shelf / "Dune.note"), "canonical name"),
        Step("copy", "b", copied, str(satchel / "Ubik.note"), "packed"),
        Step("trash", "", str(shelf / "junk.tmp"), None, "junk"),
    ]
    changes = api.carry_out(kind, steps, kernel_ctx)
    trashed = changes[2].after
    assert escort.seen == [(moved, str(shelf / "Dune.note"), True), (str(shelf / "junk.tmp"), trashed, True)], (
        "a move and a trash are escorted once each, right after they happen; a copy is not"
    )
    assert all(call.args[2] is kernel_ctx for call in escort.call_args_list), "the escort gets the context"
    escort.seen.clear()
    api.restore(kind, changes, kernel_ctx)
    assert escort.seen == [(trashed, str(shelf / "junk.tmp"), True), (str(shelf / "Dune.note"), moved, True)], (
        "undo escorts each file back, newest first"
    )


def test_no_escort_is_called_when_nothing_moved(kernel_ctx, shelf, mocker):
    escort = mocker.Mock()
    kind = FakeKind._replace(escort=escort)
    source = write_note(shelf, "draft", "Dune")
    (shelf / "Dune.note").write_text("another note")
    api.carry_out(kind, [Step("move", "id", source, str(shelf / "Dune.note"), "")], kernel_ctx)
    escort.assert_not_called()


def test_fix_and_its_undo_escort_the_kinds_companions(ctx, shelf, mocker):
    escort = mocker.Mock()
    kind = FakeKind._replace(escort=escort)
    path = write_note(shelf, "dune", "Dune")
    api.update(kind, ctx)
    assert api.act(kind, "apply", ["plan:"], ctx) == "Fixed Dune.note", "the canonical rename is applied"
    assert escort.call_args.args[:2] == (path, str(shelf / "Dune.note")), "fix escorts what it moved"
    escort.reset_mock()
    api.act(kind, "undo", [], ctx)
    assert escort.call_args.args[:2] == (str(shelf / "Dune.note"), path), "undo escorts it back"


def test_a_failing_step_does_not_stop_the_rest(kernel_ctx, shelf, mocker):
    first = write_note(shelf, "dune", "Dune")
    second = write_note(shelf, "ubik", "Ubik")
    real = os.rename
    mocker.patch.object(_steps.os, "rename", side_effect=lambda a, b: (_ for _ in ()).throw(OSError("busy")) if a == first else real(a, b))
    steps = [Step("move", "a", first, str(shelf / "Dune.note"), ""), Step("move", "b", second, str(shelf / "Ubik.note"), "")]
    changes = api.carry_out(FakeKind, steps, kernel_ctx)
    assert [change.id for change in changes] == ["b"], "the step that failed is left out, the next one runs"
