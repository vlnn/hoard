from __future__ import annotations

import time

import pytest

from hoard import _worker, api
from hoard.render import text
from hoard.testing import FakeKind
from hoard.testing.fake import write_note

MODULE = "hoard.testing.fake"


def age_index(ctx, seconds: float) -> None:
    con = api.open_database(FakeKind, api.context(FakeKind, ctx))
    con.execute("UPDATE storage_state SET last_update_at = ?", (time.time() - seconds,))
    con.commit()
    con.close()


@pytest.fixture
def indexed(ctx, shelf):
    write_note(shelf, "dune", "Dune", "Frank Herbert", "1965")
    api.update(FakeKind, ctx)
    return ctx


def test_a_fresh_index_starts_no_worker(indexed, mocker):
    spawn = mocker.patch("hoard._worker.spawn")
    api.filter(FakeKind, "dune", indexed, module=MODULE)
    spawn.assert_not_called()


def test_an_old_index_starts_the_worker_and_says_so(indexed, mocker):
    spawn = mocker.patch("hoard._worker.spawn", return_value=True)
    age_index(indexed, _worker.STALE_AFTER + 1)
    mocker.patch("hoard._worker.running", side_effect=[False, True])
    rows = text.render(api.filter(FakeKind, "dune", indexed, module=MODULE))
    spawn.assert_called_once_with(MODULE, "update", mocker.ANY)
    assert rows[0].startswith("» Updating the index…"), "the running update should be shown as usual"


def test_an_old_index_without_a_module_starts_nothing(indexed, mocker):
    spawn = mocker.patch("hoard._worker.spawn")
    age_index(indexed, _worker.STALE_AFTER + 1)
    api.filter(FakeKind, "dune", indexed)
    spawn.assert_not_called()


def test_an_empty_index_is_offered_not_refreshed(ctx, mocker):
    spawn = mocker.patch("hoard._worker.spawn")
    assert text.render(api.filter(FakeKind, "", ctx, module=MODULE)) == ["» Index is empty | ↩ to update the index"], (
        "an empty index should still ask rather than start reading on its own"
    )
    spawn.assert_not_called()


def test_a_worker_already_running_is_not_doubled(indexed, mocker):
    popen = mocker.patch("subprocess.Popen")
    age_index(indexed, _worker.STALE_AFTER + 1)
    mocker.patch("hoard._worker.running", return_value=True)
    api.filter(FakeKind, "dune", indexed, module=MODULE)
    popen.assert_not_called()
