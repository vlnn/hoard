from __future__ import annotations

import json

import pytest

from hoard.items import Head, Item, Items, Mod
from hoard.render import alfred, text


@pytest.mark.parametrize(
    "row, line",
    [
        (Item("id1", "Dune"), "Dune"),
        (Item("id1", "Dune", "Frank Herbert · 1965"), "Dune | Frank Herbert · 1965"),
        (Head("update", "Index is empty", "↩ to update the index"), "» Index is empty | ↩ to update the index"),
        (Head("none", "No match for zzz"), "» No match for zzz"),
    ],
)
def test_text_renders_each_row_as_one_line(row, line):
    assert text.render(Items((row,))) == [line], "every row should become exactly one line"


def test_text_keeps_row_order():
    items = Items((Head("a", "First"), Item("b", "Second"), Item("c", "Third")))
    assert text.render(items) == ["» First", "Second", "Third"], "lines should follow the row order"


def test_alfred_document_carries_every_key():
    items = Items(
        (
            Item(
                "id1",
                "Dune",
                "Frank",
                icon="/c/id1.jpg",
                locator="/b/Dune.note",
                verb="pack",
                mods=(Mod("shift", "open", "Open"), Mod("alt", "reveal", "Reveal in Finder")),
            ),
            Item("id2", "Bare"),
            Head("update", "Index is empty", "↩", verb="update"),
            Head("none", "No match"),
            Head("loose", "Pack all 2", "↩ on every row below", verb="pack", arg="batch:loose dune"),
        ),
        rerun=1,
    )
    expected = {
        "skipknowledge": True,
        "rerun": 1,
        "items": [
            {
                "uid": "id1",
                "title": "Dune",
                "subtitle": "Frank",
                "arg": "id1",
                "valid": True,
                "icon": {"path": "/c/id1.jpg"},
                "quicklookurl": "/b/Dune.note",
                "variables": {"verb": "pack"},
                "mods": {
                    "shift": {"arg": "id1", "subtitle": "Open", "valid": True, "variables": {"verb": "open"}},
                    "alt": {"arg": "id1", "subtitle": "Reveal in Finder", "valid": True, "variables": {"verb": "reveal"}},
                },
                "text": {"copy": "/b/Dune.note", "largetype": "Dune"},
            },
            {
                "uid": "id2",
                "title": "Bare",
                "subtitle": "",
                "arg": "id2",
                "valid": True,
                "variables": {"verb": "open"},
                "text": {"copy": "Bare", "largetype": "Bare"},
            },
            {
                "title": "Index is empty",
                "subtitle": "↩",
                "arg": "head:update",
                "valid": True,
                "variables": {"verb": "update"},
            },
            {"title": "No match", "subtitle": "", "arg": "head:none", "valid": False},
            {
                "title": "Pack all 2",
                "subtitle": "↩ on every row below",
                "arg": "batch:loose dune",
                "valid": True,
                "variables": {"verb": "pack"},
            },
        ],
    }
    assert json.loads(alfred.render(items)) == expected, "the Alfred document should match the script-filter schema"


def test_alfred_omits_rerun_when_nothing_is_running():
    assert "rerun" not in json.loads(alfred.render(Items())), "rerun should only appear while work is in progress"


def test_alfred_completion_head_extends_the_query_on_return():
    document = alfred.document(Items((Head("complete:update", "fk update", "↩ to complete", complete="update "),)))
    assert document["items"][0] == {
        "title": "fk update",
        "subtitle": "↩ to complete",
        "arg": "head:complete:update",
        "valid": False,
        "autocomplete": "update ",
    }, "a completion head should be invalid with an autocomplete, so ↩ and ⇥ fill the query"
