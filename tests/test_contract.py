from __future__ import annotations

import pytest

from hoard.contract import (
    Change,
    Command,
    Context,
    ContractError,
    Entity,
    Found,
    Kind,
    Sighting,
    Storage,
    Verb,
    lazy,
    lines_from,
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


def nothing_changes(founds, ctx):
    return []


def found(*storages, reachable=()):
    sightings = tuple(
        Sighting("x", name, f"/{name}/x", 1.0, 1, reachable=name in reachable) for name in storages
    )
    return Found(Entity("x", "X"), sightings)


def test_a_kind_needs_only_storages_fields_and_evidence():
    kind = a_kind()
    assert kind.verbs == {}, "a kind without verbs should get an empty verb map"
    assert kind.commands == {}, "a kind without commands should get an empty command map"
    assert kind.default_verb(found("library")) == "open", "the default verb should be open"
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
        ({"verbs": {"pack": "not a verb"}}, "verbs should be Verb records"),
        ({"verbs": {"open": Verb("Open", nothing_changes)}}, "open belongs to the kernel"),
        ({"verbs": {"undo": Verb("Undo", nothing_changes)}}, "undo belongs to the kernel"),
        ({"commands": {"stats": Command("Stats", "open")}}, "stats belongs to the kernel"),
        ({"commands": {"loose": Command("Pack", "pack")}}, "a command should name a verb that exists"),
        ({"commands": {"Loose": Command("Open", "open")}}, "a command word should be one lowercase word"),
        ({"commands": {"loose": Command("Open", "open", on=("device",))}}, "on should name the kind's storages"),
        ({"labels": {"plural": "books"}}, "labels should be from the known set"),
        ({"derive": {"ocr": "not callable"}}, "derived producers should be callable"),
        ({"nameable": ("publisher",)}, "nameable should name the kind's fields"),
        ({"tags": ("scifi",)}, "tags should be a callable taking the context"),
        ({"pictured_first": "yes"}, "pictured_first should be a bool"),
        ({"derive": {"OCR text": str}}, "derived keys should be lowercase identifiers"),
        ({"labels": {"one": 1}}, "labels should be strings"),
        ({"commands": {"loose": Command("Open", "open", off=("device",))}}, "off should name the kind's storages"),
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


@pytest.mark.parametrize("verb", ["open", "reveal"])
def test_commands_may_use_kernel_verbs(verb):
    kind = a_kind(commands={"all": Command("Open", verb)})
    assert kind.commands["all"].verb == verb, "open and reveal are available to every command"


def test_commands_keep_everything_by_default():
    assert Command("Open", "open").keep(found("library")), "a command without a filter should keep every row"


@pytest.mark.parametrize(
    "storages, reachable, nearest",
    [
        (("device", "library"), ("device", "library"), "device"),
        (("device", "library"), ("library",), "library"),
        (("device", "library"), (), "device"),
        (("library",), ("library",), "library"),
    ],
)
def test_nearest_is_the_first_reachable_sighting_in_kind_order(storages, reachable, nearest):
    assert found(*storages, reachable=reachable).nearest.storage == nearest, (
        "the nearest copy should be the first reachable one, else the first one"
    )


def test_found_answers_where_an_entity_is():
    sighted = found("device", "library", reachable=("library",))
    assert sighted.storages == ("device", "library"), "storages should list every place, in kind order"
    assert sighted.on("device") and not sighted.on("satchel"), "on() should say whether a storage holds it"
    assert sighted.locator_in("library") == "/library/x", "locator_in() should give that storage's copy"
    assert sighted.locator_in("satchel") is None, "a storage without a copy has no locator"


def test_context_carries_the_roots_of_every_storage():
    ctx = Context(data="/d", cache="/c", roots={"device": ("/Volumes/KOBO",)})
    assert ctx.roots_of("device") == ("/Volumes/KOBO",), "verbs should find storage roots in the context"
    assert ctx.roots_of("satchel") == (), "an unknown storage has no roots"


def test_lines_from_reads_one_value_per_line():
    tags = lines_from("tags")
    assert tags(Context(data="", cache="", config={"tags": "scifi\n fantasy \n\n"})) == ["scifi", "fantasy"], (
        "a lines setting should give its non-blank lines"
    )
