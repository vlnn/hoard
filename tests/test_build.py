from __future__ import annotations

import os
import plistlib
import zipfile
from pathlib import Path

import pytest

pytest.importorskip("tomllib")

from hoard import build, new  # noqa: E402

LIBRARY = Path(__file__).resolve().parents[1]

CONFIGURATION = """
[[configuration]]
variable = "shelf"
label = "Shelf folders"
type = "lines"
description = "One folder per line"

[[configuration]]
variable = "nickname"
label = "Nickname"
type = "text"
default = "mine"

[[configuration]]
variable = "archive"
label = "Archive folder"
type = "folder"

[[configuration]]
variable = "verbose"
label = "Verbose"
type = "checkbox"
"""


@pytest.fixture
def repo(tmp_path, monkeypatch):
    root = new.write_kind_repository("shelf", tmp_path / "repos", keyword="sh", hoard_source=LIBRARY)
    with open(root / "workflow" / "plist.toml", "a") as handle:
        handle.write(CONFIGURATION)
    monkeypatch.syspath_prepend(str(root))
    return root


@pytest.fixture
def plist(repo):
    return build.info_plist(build.read_workflow(repo), keyword="sh")


def objects_by_type(plist):
    return {item["type"]: item for item in plist["objects"]}


def test_workflow_reads_the_plist_toml(repo):
    workflow = build.read_workflow(repo)
    assert (workflow.kind, workflow.name, workflow.bundleid) == ("shelf", "Shelf", "com.example.hoard.shelf"), (
        "the workflow should come from workflow/plist.toml"
    )
    assert [s.variable for s in workflow.configuration] == ["shelf", "nickname", "archive", "verbose"], (
        "configuration should keep its order"
    )


def test_script_filter_runs_the_system_python(plist):
    script_filter = objects_by_type(plist)["alfred.workflow.input.scriptfilter"]["config"]
    assert script_filter["keyword"] == "sh", "the keyword should come from KIND"
    assert script_filter["script"] == '/usr/bin/python3 hoard.py filter "$1"', "the filter should run the system python"
    assert script_filter["alfredfiltersresults"] is False, "hoard does its own matching"


def test_action_runs_the_verb_from_the_row_variables(plist):
    action = objects_by_type(plist)["alfred.workflow.action.script"]["config"]
    assert action["script"] == '/usr/bin/python3 hoard.py act "$verb" "$1"', "the action should pass the row's verb"


def test_objects_are_chained_filter_action_notification(plist):
    uid = {kind: item["uid"] for kind, item in objects_by_type(plist).items()}
    chain = {
        source: [link["destinationuid"] for link in links] for source, links in plist["connections"].items()
    }
    assert chain == {
        uid["alfred.workflow.input.scriptfilter"]: [uid["alfred.workflow.action.script"]],
        uid["alfred.workflow.action.script"]: [uid["alfred.workflow.output.notification"]],
    }, "the filter should feed the action, the action the notification"


@pytest.mark.parametrize(
    "variable, alfred_type, config",
    [
        ("shelf", "textarea", {"default": "", "required": False, "trim": True, "verticalsize": 3}),
        ("nickname", "textfield", {"default": "mine", "placeholder": "", "required": False, "trim": True}),
        ("archive", "filepicker", {"default": "", "filtermode": 1, "placeholder": "", "required": False}),
        ("verbose", "checkbox", {"default": False, "required": False, "text": ""}),
    ],
)
def test_configuration_becomes_alfred_user_configuration(plist, variable, alfred_type, config):
    entry = next(e for e in plist["userconfigurationconfig"] if e["variable"] == variable)
    assert (entry["type"], entry["config"]) == (alfred_type, config), f"{variable} should map to an Alfred {alfred_type}"


def test_uids_are_stable_between_builds(repo):
    workflow = build.read_workflow(repo)
    first, second = build.info_plist(workflow, "sh"), build.info_plist(workflow, "sh")
    assert [o["uid"] for o in first["objects"]] == [o["uid"] for o in second["objects"]], (
        "Alfred keys settings by uid, so uids should not change between builds"
    )


def test_bundle_holds_two_packages_and_nothing_to_develop_with(repo):
    path = build.bundle(repo)
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
    assert path == repo / "dist" / "shelf.alfredworkflow", "the bundle should land in dist/"
    assert {"info.plist", "hoard.py", "icon.png", "version.json", "hoard/api.py", "shelf/__init__.py"} <= names, (
        "the bundle should hold the plist, the entry script, the icon, the library and the kind"
    )
    unwanted = [n for n in names if n.startswith(("hoard/testing/", "hoard/build/", "hoard/template/", "hoard/new.py")) or "__pycache__" in n]
    assert unwanted == [], "development-only parts of the library should stay out of the bundle"


def test_bundle_plist_is_a_valid_property_list(repo):
    with zipfile.ZipFile(build.bundle(repo)) as archive:
        plist = plistlib.loads(archive.read("info.plist"))
    assert plist["bundleid"] == "com.example.hoard.shelf", "info.plist should parse and carry the bundle id"


def test_check_answers_a_keystroke_from_the_built_bundle(repo):
    assert build.check(repo) == "ok: Index is empty", "the built bundle should answer an empty filter"


def test_check_fails_when_the_bundle_cannot_answer(repo):
    (repo / "shelf" / "__init__.py").write_text("raise RuntimeError('broken kind')\n")
    with pytest.raises(build.BuildError):
        build.check(repo)


def test_link_points_the_installed_workflow_at_both_checkouts(repo, tmp_path):
    installed = build.link(repo, tmp_path / "workflows")
    assert installed.name == "user.workflow.com.example.hoard.shelf", "the folder should be named for the bundle id"
    assert os.path.realpath(installed / "shelf") == str((repo / "shelf").resolve()), "the kind should be a symlink"
    assert os.path.realpath(installed / "hoard") == str((LIBRARY / "src" / "hoard").resolve()), "hoard should be a symlink"
    assert (installed / "info.plist").is_file(), "the plist should be a real file Alfred can read"


def test_link_twice_replaces_the_previous_link(repo, tmp_path):
    build.link(repo, tmp_path / "workflows")
    installed = build.link(repo, tmp_path / "workflows")
    assert (installed / "hoard.py").is_file(), "relinking should leave a working workflow"


def test_check_passes_for_a_kind_whose_folders_are_not_set_yet(repo):
    (repo / "shelf" / "__init__.py").write_text(
        "from hoard.contract import Kind, Storage, roots_from\n"
        "KIND = Kind(name='shelf', keyword='sh', fields=('path',), evidence=str,\n"
        "            storages=(Storage('shelf', roots_from('shelf'), str),))\n"
    )
    assert build.check(repo) == "ok: Index is empty", "rows explaining missing folders should not fail the check"


def hoard_variables(plist) -> list:
    return [entry["variable"] for entry in plist["userconfigurationconfig"] if entry["variable"].startswith("hoard_")]


def test_model_settings_follow_the_kinds_own(repo):
    plist = build.info_plist(build.read_workflow(repo), keyword="sh", roles=("embeddings",))
    variables = [entry["variable"] for entry in plist["userconfigurationconfig"]]
    assert variables[-3:] == ["hoard_embeddings_url", "hoard_embeddings_key", "hoard_ask_on_update"], (
        "the model settings belong to hoard and should follow the kind's own"
    )


def test_a_kind_without_model_work_gets_no_model_settings(repo):
    (repo / "shelf" / "__init__.py").write_text(
        "from hoard.contract import Kind, Storage, roots_from\n"
        "KIND = Kind(name='shelf', keyword='sh', fields=('path',), evidence=str, like=None,\n"
        "            storages=(Storage('shelf', roots_from('shelf'), str),))\n"
    )
    with zipfile.ZipFile(build.bundle(repo)) as archive:
        plist = plistlib.loads(archive.read("info.plist"))
    assert hoard_variables(plist) == [], "pictures and the like should not be asked for model servers"


def test_the_template_kind_is_asked_for_an_embeddings_server(repo):
    with zipfile.ZipFile(build.bundle(repo)) as archive:
        plist = plistlib.loads(archive.read("info.plist"))
    assert hoard_variables(plist) == ["hoard_embeddings_url", "hoard_embeddings_key", "hoard_ask_on_update"], (
        "a kind with the default text like should be offered the embeddings server"
    )
