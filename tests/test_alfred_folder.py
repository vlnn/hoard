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
