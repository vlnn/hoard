from __future__ import annotations

import json
import subprocess
import sys

import pytest

from hoard import cli
from hoard.testing.fake import read_note, write_note

FAKE = "hoard.testing.fake"


@pytest.fixture
def alfred(monkeypatch, ctx):
    monkeypatch.setenv("alfred_workflow_data", ctx.data)
    monkeypatch.setenv("alfred_workflow_cache", ctx.cache)
    for name, value in ctx.config.items():
        monkeypatch.setenv(name, value)
    return ctx


@pytest.fixture
def dune(shelf):
    return read_note(write_note(shelf, "dune", "Dune", "Frank Herbert", "1965"))


def run(capsys, *argv):
    cli.main(FAKE, list(argv))
    return capsys.readouterr().out


def test_filter_prints_script_filter_json(alfred, capsys):
    document = json.loads(run(capsys, "filter", "dune"))
    assert document["items"][0]["title"] == "Index is empty", "filter should print Alfred's JSON"


def test_filter_text_prints_lines(alfred, dune, capsys):
    run(capsys, "update")
    assert run(capsys, "filter", "--text", "dune").splitlines()[0].startswith("Dune | Frank Herbert"), (
        "--text should print the plain-text rendering"
    )


def test_filter_without_a_query_lists_newest(alfred, dune, capsys):
    run(capsys, "update")
    assert json.loads(run(capsys, "filter"))["items"][0]["uid"] == dune.id, "a missing query should mean empty"


def test_update_prints_how_many_were_found(alfred, dune, capsys):
    assert run(capsys, "update") == "1 found\n", "update should report its count"


def test_act_open_prints_the_notification_line(alfred, dune, capsys, mocker):
    mocker.patch("subprocess.run")
    run(capsys, "update")
    assert run(capsys, "act", "open", dune.id) == "Opened Dune\n", "act should print the notification text"


def test_act_update_starts_the_worker(alfred, capsys, mocker):
    spawn = mocker.patch("hoard._worker.spawn", return_value=True)
    assert run(capsys, "act", "update", "head:update") == "Updating the index\n", "update should go to the worker"
    assert spawn.call_args.args[:2] == (FAKE, "update"), "the worker should be told which kind to update"


def test_act_update_while_running_says_so(alfred, capsys, mocker):
    mocker.patch("hoard._worker.spawn", return_value=False)
    assert run(capsys, "act", "update") == "Already updating\n", "a second update should not start a worker"


@pytest.mark.parametrize("ok, code", [(True, 0), (False, 1)])
def test_doctor_exit_code_follows_the_report(alfred, capsys, mocker, ok, code):
    mocker.patch("hoard._doctor.fts5_available", return_value=ok)
    with pytest.raises(SystemExit) as exit_info:
        run(capsys, "doctor")
    assert exit_info.value.code == code, "doctor should exit non-zero when a required check fails"


@pytest.mark.parametrize("argv", [[], ["juggle"]])
def test_unknown_mode_prints_usage(alfred, capsys, argv):
    with pytest.raises(SystemExit) as exit_info:
        cli.main(FAKE, argv)
    assert exit_info.value.code == 2, "an unknown mode should exit with usage"
    assert "usage" in capsys.readouterr().err, "usage should go to stderr"


def test_module_entry_point_takes_the_kind_first(alfred):
    finished = subprocess.run(
        [sys.executable, "-m", "hoard", FAKE, "filter", "--text", ""], capture_output=True, text=True
    )
    assert finished.stdout == "» Index is empty | ↩ to update the index\n", "python -m hoard <kind> should work"
