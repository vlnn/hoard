from __future__ import annotations

import urllib.error

import pytest

from hoard import _doctor, api
from hoard.testing import FakeKind


def statuses(report):
    return {check.name: check.status for check in report.checks}


def test_doctor_passes_on_this_machine(ctx):
    report = api.doctor(FakeKind, ctx)
    assert report.ok, f"doctor should pass where FTS5 exists: {report.lines()}"
    assert statuses(report)["fts5"] == "ok", "FTS5 should be found"


@pytest.mark.parametrize(
    "missing, check, status, ok",
    [
        ("fts5_available", "fts5", "fail", False),
        ("trigram_available", "trigram", "warn", True),
    ],
)
def test_doctor_grades_missing_sqlite_features(ctx, mocker, missing, check, status, ok):
    mocker.patch(f"hoard._doctor.{missing}", return_value=False)
    report = api.doctor(FakeKind, ctx)
    assert statuses(report)[check] == status, f"a missing {check} should be a {status}"
    assert report.ok is ok, f"a missing {check} should {'not ' if ok else ''}fail doctor"


def test_doctor_reports_each_storage_root(ctx, satchel):
    satchel.rmdir()
    report = statuses(api.doctor(FakeKind, ctx))
    assert report["storage shelf"] == "ok", "a mounted root should be fine"
    assert report["storage satchel"] == "warn", "an unmounted root should be a warning, not a failure"


def test_doctor_warns_about_an_unconfigured_storage(context_with):
    report = api.doctor(FakeKind, context_with())
    shelf = next(c for c in report.checks if c.name == "storage shelf")
    assert (shelf.status, shelf.value) == ("warn", "no folder configured (fake_shelf)"), (
        "a storage without roots should name the setting to fill in"
    )


def test_doctor_lines_align_status_name_and_value():
    report = _doctor.Report((_doctor.Check("python", "3.9.6", "ok"), _doctor.Check("fts5", "missing", "fail")))
    assert report.lines() == ["ok    python           3.9.6", "FAIL  fts5             missing"], (
        "lines should be readable in a terminal"
    )


@pytest.mark.parametrize(
    "reply, status, value",
    [
        ({"data": [{"id": "qwen"}]}, "ok", "http://m:8080 · qwen"),
        (urllib.error.URLError("refused"), "warn", "http://m:8080 not reachable: refused"),
    ],
)
def test_doctor_checks_each_configured_model_server(ctx, replies, reply, status, value):
    replies(reply)
    report = api.doctor(FakeKind, ctx._replace(config={**ctx.config, "hoard_chat_url": "http://m:8080"}))
    (check,) = [c for c in report.checks if c.name == "chat server"]
    assert (check.status, check.value) == (status, value), "doctor should say whether the model server answers"
