from __future__ import annotations

import pytest

from hoard.contract import (
    Change,
    Context,
    ContractError,
    Entity,
    Kind,
    Storage,
    Verb,
    lazy,
    roots_from,
)


def read_nothing(path):
    return None


def evidence(entity):
    return entity.title


def a_kind(**overrides):
    parts = dict(
        name="shelf",
        keyword="sh",
        storages=(Storage("library", roots_from("library"), read_nothing),),
        fields=("author", "path"),
        evidence=evidence,
    )
    parts.update(overrides)
    return Kind(**parts)


def test_a_kind_needs_only_storages_fields_and_evidence():
    kind = a_kind()
    assert kind.verbs == {}, "a kind without verbs should get an empty verb map"
    assert kind.commands == {}, "a kind without commands should get an empty command map"
    assert kind.default_verb(Entity("x", "X")) == "open", "the default verb should be open"
    assert kind.icon(Entity("x", "X")) is None, "a kind without icons should draw none"


@pytest.mark.parametrize(
    "overrides, reason",
    [
        ({"name": "Shelf Books"}, "a name with spaces cannot name a database"),
        ({"name": ""}, "an empty name cannot name a database"),
        ({"keyword": ""}, "an empty keyword cannot open the workflow"),
        ({"fields": ("author", 3)}, "every field label should be a string"),
        ({"fields": ["author"]}, "fields should be an ordered tuple"),
        ({"storages": [Storage("a", roots_from("a"), read_nothing)]}, "storages should be an ordered tuple"),
        (
            {"storages": (Storage("a", roots_from("a"), read_nothing), Storage("a", roots_from("b"), read_nothing))},
            "storage names should be unique",
        ),
        ({"evidence": "title"}, "evidence should be callable"),
        ({"verbs": {"open": "not a verb"}}, "verbs should be Verb records"),
    ],
)
def test_a_malformed_kind_fails_when_built(overrides, reason):
    with pytest.raises(ContractError):
        a_kind(**overrides)
        pytest.fail(reason)


@pytest.mark.parametrize(
    "setting, expected",
    [
        ("", []),
        ("/books", ["/books"]),
        ("/books\n/more books\n", ["/books", "/more books"]),
        ("  /books  \n\n", ["/books"]),
    ],
)
def test_roots_from_reads_one_folder_per_line_of_a_setting(setting, expected):
    roots = roots_from("library")
    ctx = Context(data="/d", cache="/c", config={"library": setting})
    assert roots(ctx) == expected, "roots should be the non-blank lines of the setting"


def test_lazy_imports_its_target_on_first_call():
    join = lazy("os.path", "join")
    assert join("a", "b") == "a/b", "a lazy callable should behave like its target"


def test_lazy_names_its_target():
    assert "os.path:join" in repr(lazy("os.path", "join")), "a lazy callable should say what it stands for"


def test_verb_without_undo_is_not_undoable():
    assert not Verb("Play", run=lambda ids, ctx: []).undoable, "a verb with undo=None should not be undoable"


def test_change_is_a_plain_value():
    change = Change("id1", "move", "/a", "/b")
    assert change == Change("id1", "move", "/a", "/b"), "changes should compare by value"
