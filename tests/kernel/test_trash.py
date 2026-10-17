from __future__ import annotations

import os

import pytest

from hoard import _trash, api
from hoard.contract import Step
from hoard.render import text
from hoard.testing import FakeKind
from hoard.testing.fake import write_note


def lines(ctx, typed="fix"):
    return text.render(api.filter(FakeKind, typed, ctx))


@pytest.fixture
def trashed(ctx, shelf):
    write_note(shelf, "Ubik", "Ubik")
    kernel_ctx = api.context(FakeKind, ctx)
    (shelf / "a.tmp").write_bytes(b"12345")
    (shelf / "deep" / "b.tmp").parent.mkdir()
    (shelf / "deep" / "b.tmp").write_bytes(b"1234567")
    steps = [Step("trash", "", str(shelf / "a.tmp"), None, "junk"), Step("trash", "", str(shelf / "deep" / "b.tmp"), None, "junk")]
    api.carry_out(FakeKind, steps, kernel_ctx)
    return ctx


def test_a_clean_tree_without_a_trash_has_nothing_to_fix(ctx, shelf):
    write_note(shelf, "Dune", "Dune")
    api.update(FakeKind, ctx)
    assert lines(ctx) == ["» Nothing to fix"], "no trash, no row"


def test_fix_offers_to_empty_a_trash_that_holds_something(trashed):
    api.update(FakeKind, trashed)
    assert lines(trashed) == ["» Empty the trash | 2 items · 12 B · cannot be undone"], (
        "the trash row counts what the trash holds and says it is final"
    )


def test_the_trash_row_comes_after_the_plan(trashed, shelf):
    write_note(shelf, "dune", "Dune")
    api.update(FakeKind, trashed)
    assert lines(trashed)[0].startswith("» Apply 1") and lines(trashed)[-1].startswith("» Empty the trash"), (
        "the plan comes first, the trash row last"
    )


def test_emptying_the_trash_removes_it_for_good(trashed, shelf):
    api.update(FakeKind, trashed)
    assert api.act(FakeKind, "empty_trash", [], trashed) == "Emptied the trash: 2 items", "the notification counts what went"
    assert not (shelf / ".hoard-trash").exists(), "the trash folder itself is gone"
    assert api.act(FakeKind, "undo", [], trashed) == "Nothing to undo", "emptying is not a batch to undo"
    assert lines(trashed) == ["» Nothing to fix"], "and the row is gone"


def test_contents_count_files_and_bytes_under_every_root(trashed, satchel):
    (satchel / ".hoard-trash").mkdir()
    (satchel / ".hoard-trash" / "c.note").write_bytes(b"x" * 100)
    kernel_ctx = api.context(FakeKind, trashed)
    assert _trash.contents(FakeKind, kernel_ctx) == (3, 112), "every storage's trash counts"


@pytest.mark.parametrize("size, shown", [(0, "0 B"), (999, "999 B"), (1536, "1.5 KB"), (2_500_000, "2.4 MB"), (3_000_000_000, "2.8 GB")])
def test_sizes_read_the_way_finder_shows_them(size, shown):
    assert _trash.human(size) == shown, f"{size} bytes should read {shown}"


def test_a_trash_outside_the_kinds_ground_is_left_alone(trashed, tmp_path):
    elsewhere = tmp_path / "elsewhere" / ".hoard-trash"
    elsewhere.mkdir(parents=True)
    (elsewhere / "keep.txt").write_text("mine")
    api.act(FakeKind, "empty_trash", [], trashed)
    assert os.path.exists(elsewhere / "keep.txt"), "only the trash under the kind's own folders is emptied"
