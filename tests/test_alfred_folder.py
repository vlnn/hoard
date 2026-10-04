from __future__ import annotations

import plistlib

import pytest

from hoard import _alfred

BUNDLE = "com.example.hoard.shelf"


@pytest.fixture
def workflow(tmp_path):
    (tmp_path / "info.plist").write_bytes(plistlib.dumps({"bundleid": BUNDLE}))
    (tmp_path / "prefs.plist").write_bytes(plistlib.dumps({"fake_shelf": "/Volumes/Shelf", "verbose": True}))
    return tmp_path


@pytest.mark.parametrize(
    "variable, expected",
    [
        ("alfred_workflow_bundleid", BUNDLE),
        ("alfred_workflow_data", f"/Users/va/Library/Application Support/Alfred/Workflow Data/{BUNDLE}"),
        ("alfred_workflow_cache", f"/Users/va/Library/Caches/com.runningwithcrayons.Alfred/Workflow Data/{BUNDLE}"),
        ("fake_shelf", "/Volumes/Shelf"),
        ("verbose", "True"),
    ],
)
def test_an_installed_workflow_supplies_what_alfred_would(workflow, variable, expected):
    environ = {"HOME": "/Users/va"}
    _alfred.fill_from_workflow(str(workflow), environ)
    assert environ[variable] == expected, f"{variable} should be filled the way Alfred fills it"


def test_variables_already_set_win(workflow):
    environ = {"HOME": "/Users/va", "fake_shelf": "/elsewhere"}
    _alfred.fill_from_workflow(str(workflow), environ)
    assert environ["fake_shelf"] == "/elsewhere", "an explicit variable should beat the saved configuration"


def test_a_folder_that_is_not_a_workflow_changes_nothing(tmp_path):
    environ = {"HOME": "/Users/va"}
    _alfred.fill_from_workflow(str(tmp_path), environ)
    assert environ == {"HOME": "/Users/va"}, "outside a workflow nothing should be invented"


def declaring(folder, *variables):
    plist = {"bundleid": BUNDLE, "userconfigurationconfig": [{"variable": v, "label": v.title()} for v in variables]}
    (folder / "info.plist").write_bytes(plistlib.dumps(plist))


def test_declared_settings_come_from_the_installed_plist(tmp_path):
    declaring(tmp_path, "fake_shelf", "fake_satchel")
    assert _alfred.declared_settings(str(tmp_path)) == [("fake_shelf", "Fake_Shelf"), ("fake_satchel", "Fake_Satchel")], (
        "doctor should know every setting the workflow declares, in order"
    )


def test_outside_a_workflow_no_settings_are_declared(tmp_path):
    assert _alfred.declared_settings(str(tmp_path)) == [], "a folder without info.plist declares nothing"


def test_doctor_reports_each_declared_setting(tmp_path, ctx):
    from hoard import api
    from hoard.testing import FakeKind

    config = {"fake_shelf": "/Volumes/Shelf\n/Volumes/Other\n"}
    report = api.doctor(FakeKind, ctx._replace(config=config), settings=[("fake_shelf", "Shelf"), ("fake_satchel", "Satchel")])
    lines = [line for line in report.lines() if "setting" in line]
    assert lines == [
        "ok    setting          Shelf: /Volumes/Shelf · /Volumes/Other",
        "warn  setting          Satchel: not set",
    ], "doctor should show each declared setting and flag the empty ones"
