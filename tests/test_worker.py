from __future__ import annotations

import os
import subprocess
import sys

import pytest

from hoard import _db, _worker


def write_lock(ctx, pid):
    with open(_worker.lock_path(ctx), "w") as handle:
        handle.write(str(pid))


def test_nothing_is_running_without_a_lock(ctx):
    assert not _worker.running(ctx), "no lock file should mean no worker"


def test_a_lock_held_by_a_live_process_means_running(ctx):
    write_lock(ctx, os.getpid())
    assert _worker.running(ctx), "a lock whose pid is alive should mean a worker runs"


@pytest.mark.parametrize("content", ["4242", "not a pid", ""])
def test_a_stale_lock_is_removed(ctx, mocker, content):
    mocker.patch("os.kill", side_effect=ProcessLookupError)
    with open(_worker.lock_path(ctx), "w") as handle:
        handle.write(content)
    assert not _worker.running(ctx), "a lock whose pid is gone should not count as running"
    assert not os.path.exists(_worker.lock_path(ctx)), "a stale lock should be removed on the next check"


def test_holding_the_lock_writes_the_pid_and_releases_it(ctx):
    with _worker.holding_lock(ctx):
        assert _worker.read_pid(_worker.lock_path(ctx)) == os.getpid(), "the lock should hold the worker's pid"
    assert not os.path.exists(_worker.lock_path(ctx)), "the lock should be released after the job"


def test_a_held_lock_refuses_a_second_worker(ctx):
    with _worker.holding_lock(ctx):
        with pytest.raises(_worker.Busy):
            with _worker.holding_lock(ctx):
                pytest.fail("a second worker should not get the lock")


def test_spawn_detaches_a_worker(ctx, mocker):
    popen = mocker.patch("subprocess.Popen")
    assert _worker.spawn("books", "update", ctx), "spawn should report that it started a worker"
    command = popen.call_args.args[0]
    assert command == [sys.executable, "-m", "hoard", "books", "worker", "update"], "the worker re-enters through -m hoard"
    assert popen.call_args.kwargs["start_new_session"], "the worker should outlive the script filter"
    assert popen.call_args.kwargs["stdin"] == subprocess.DEVNULL, "the worker should not hold Alfred's stdin"


def test_spawn_does_nothing_while_a_worker_runs(ctx, mocker):
    popen = mocker.patch("subprocess.Popen")
    write_lock(ctx, os.getpid())
    assert not _worker.spawn("books", "update", ctx), "spawn should not start a second worker"
    popen.assert_not_called()


def test_worker_environment_puts_the_library_first_on_the_path():
    paths = _worker.worker_environment()["PYTHONPATH"].split(os.pathsep)
    assert os.path.isdir(os.path.join(paths[0], "hoard")), "the worker should import the same hoard as its parent"


def test_a_real_worker_run_indexes_and_releases_the_lock(ctx, shelf):
    from hoard.testing.fake import write_note

    write_note(shelf, "dune", "Dune", "Frank Herbert", "1965")
    environ = dict(_worker.worker_environment())
    environ.update(ctx.config, alfred_workflow_data=ctx.data, alfred_workflow_cache=ctx.cache)
    finished = subprocess.run(
        _worker.worker_command("hoard.testing.fake", "update"), env=environ, capture_output=True, text=True
    )
    assert finished.returncode == 0, f"the worker should exit cleanly: {finished.stderr}"
    con = _db.connect(_db.path_for("fake", ctx.data))
    assert con.execute("SELECT title FROM entities").fetchall() == [("Dune",)], "the worker should index the shelf"
    assert con.execute("SELECT count FROM storage_state WHERE storage = 'shelf'").fetchone() == (1,), (
        "the worker should leave its count in storage_state"
    )
    con.close()
    assert not _worker.running(ctx), "the lock should be gone after the run"
