from __future__ import annotations

import pytest

from hoard import _db

pytest_plugins = ["hoard.testing"]


@pytest.fixture
def tmp_db(tmp_path):
    con = _db.connect(str(tmp_path / "kind.sqlite"))
    yield con
    con.close()


@pytest.fixture
def shelf(tmp_path):
    return tmp_path / "shelf"


@pytest.fixture
def satchel(tmp_path):
    return tmp_path / "satchel"


@pytest.fixture
def ctx(context_with, shelf, satchel):
    return context_with(fake_shelf=str(shelf), fake_satchel=str(satchel))
