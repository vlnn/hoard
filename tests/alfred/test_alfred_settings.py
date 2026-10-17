import os

import pytest

from hoard.alfred.settings import cache_folder, data_folder, is_on


@pytest.mark.parametrize("value", ["1", "true", "YES", " on "])
def test_a_checkbox_is_on(value):
    assert is_on(value) is True, f"{value!r} is how Alfred and a shell spell a ticked box"


@pytest.mark.parametrize("value", ["", "0", "false", "off", "no"])
def test_a_checkbox_is_off(value):
    assert is_on(value) is False, f"{value!r} should read as off"


def test_alfred_folders_win_when_alfred_set_them():
    environ = {"alfred_workflow_data": "/d", "alfred_workflow_cache": "/c"}
    assert (data_folder(environ, "wisp"), cache_folder(environ, "wisp")) == ("/d", "/c"), "inside Alfred the folders are given"


def test_outside_alfred_the_folders_follow_xdg_then_home():
    environ = {"XDG_DATA_HOME": "/xdg/data"}
    assert data_folder(environ, "wisp") == "/xdg/data/hoard/wisp", "XDG_DATA_HOME, then hoard, then the workflow's name"
    assert cache_folder(environ, "wisp") == os.path.expanduser("~/.cache/hoard/wisp"), "without XDG_CACHE_HOME the home default"
