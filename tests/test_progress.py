from __future__ import annotations

import pytest

from hoard import _db, _progress


@pytest.fixture
def watcher(tmp_db):
    con = _db.connect(tmp_db.execute("PRAGMA database_list").fetchone()[2])
    yield con
    con.close()


def test_a_database_with_no_job_reports_an_update_counting_its_files(tmp_db):
    assert _progress.current(tmp_db) == ("update", "0", ""), "no recorded job should read as an update still counting"


@pytest.mark.parametrize("job, total", [("update", ""), ("update", 2150), ("ask", 2150), ("embed", 16)])
def test_beginning_a_job_is_visible_to_other_connections(tmp_db, watcher, job, total):
    _progress.begin(tmp_db, job, total)
    assert _progress.current(watcher) == (job, "0", str(total)), "a begun job should be committed with nothing done yet"


def test_counting_sets_the_total_of_the_running_job(tmp_db, watcher):
    _progress.begin(tmp_db, "update")
    _progress.count(tmp_db, 3)
    assert _progress.current(watcher) == ("update", "0", "3"), "the total should arrive once the files are counted"


def test_advancing_is_visible_to_other_connections(tmp_db, watcher):
    _progress.begin(tmp_db, "ask", 2)
    _progress.advance(tmp_db, 1)
    assert _progress.current(watcher) == ("ask", "1", "2"), "each step should be committed for the filter to see"


@pytest.mark.parametrize("done, committed", [(1, "0"), (2, "0"), (3, "3"), (4, "3"), (6, "6")])
def test_ticking_commits_only_every_few_steps(tmp_db, watcher, mocker, done, committed):
    mocker.patch("hoard._progress.EVERY", 3)
    _progress.begin(tmp_db, "update", 10)
    for step in range(1, done + 1):
        _progress.tick(tmp_db, step)
    assert _progress.current(watcher).done == committed, "cheap steps should commit their count every few steps only"
