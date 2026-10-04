from __future__ import annotations

import json

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
    shelf.mkdir()
    satchel.mkdir()
    return context_with(fake_shelf=str(shelf), fake_satchel=str(satchel))


@pytest.fixture
def replies(mocker):
    def answer(*bodies):
        responses = []
        for body in bodies:
            if isinstance(body, BaseException):
                responses.append(body)
                continue
            response = mocker.MagicMock()
            raw = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
            response.__enter__.return_value.read.return_value = raw
            responses.append(response)
        return mocker.patch("urllib.request.urlopen", side_effect=responses)

    return answer
