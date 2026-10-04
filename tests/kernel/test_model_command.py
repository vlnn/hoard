from __future__ import annotations

import urllib.error

import pytest

from hoard import _db, _models, api
from hoard.render import text
from hoard.testing import FakeKind
from hoard.testing.fake import write_note

SERVERS = {"hoard_chat_url": "http://m:8080", "hoard_embeddings_url": "http://e:8081"}


@pytest.fixture
def served(context_with, shelf, satchel):
    shelf.mkdir()
    satchel.mkdir()
    write_note(shelf, "dune", "Dune")
    ctx = context_with(fake_shelf=str(shelf), fake_satchel=str(satchel), **SERVERS)
    api.update(FakeKind, ctx)
    return ctx


def models(*ids):
    return {"object": "list", "data": [{"id": model} for model in ids]}


def lines(ctx, typed="model"):
    return text.render(api.filter(FakeKind, typed, ctx))


def test_model_lists_what_each_server_offers(served, replies):
    replies(models("qwen", "llama"), models("nomic"))
    con = _db.connect(_db.path_for("fake", served.data))
    _models.use(con, "chat", "llama")
    con.commit()
    con.close()
    assert lines(served) == [
        "» Chat models | http://m:8080",
        "qwen | chat · ↩ to use",
        "llama | chat · in use",
        "» Embeddings models | http://e:8081",
        "nomic | embeddings · ↩ to use",
    ], "model should list each server's models and mark the one in use"


def test_an_unreachable_server_says_why(served, replies):
    replies(urllib.error.URLError("Connection refused"), models("nomic"))
    assert lines(served)[0] == "» Chat server not reachable | http://m:8080 · Connection refused", (
        "a dead server should be named, with the reason"
    )


def test_a_slow_server_gets_a_few_seconds(served, replies):
    urlopen = replies(models("qwen"), models("nomic"))
    lines(served)
    assert urlopen.call_args.kwargs["timeout"] == 3.0, "listing models should allow a server a few seconds"


def test_choosing_a_model_remembers_it(served, replies):
    replies(models("qwen"), models("nomic"))
    (row,) = [r for r in api.filter(FakeKind, "model", served).rows if getattr(r, "id", "") == "model:chat:qwen"]
    assert api.act(FakeKind, row.verb, [row.id], served) == "Chat model: qwen", "↩ should say what was chosen"
    con = _db.connect(_db.path_for("fake", served.data))
    assert _models.server(con, api.context(FakeKind, served), "chat").model == "qwen", "the choice should be stored"
    con.close()


def test_without_a_server_model_is_just_a_word(ctx, shelf):
    write_note(shelf, "dune", "Dune")
    api.update(FakeKind, ctx)
    assert not any(line.startswith("» ") for line in lines(ctx)), (
        "without a server, model should be an ordinary search word"
    )
