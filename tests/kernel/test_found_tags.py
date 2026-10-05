from __future__ import annotations

import pytest

from hoard import api
from hoard.contract import Plan, Verb
from hoard.testing import FakeKind
from hoard.testing.fake import read_note, write_note


@pytest.fixture
def tagged_shelf(context_with, shelf, satchel):
    shelf.mkdir()
    satchel.mkdir()
    ctx = context_with(fake_shelf=str(shelf), fake_satchel=str(satchel), fake_tags="scifi\nfantasy")
    ids = {
        "dune": read_note(write_note(shelf, "dune", "Dune")).id,
        "ubik": read_note(write_note(shelf, "ubik", "Ubik")).id,
    }
    api.update(FakeKind, ctx)
    choice = api.filter(FakeKind, f"tag #{ids['ubik']} scifi", ctx).rows[1]
    api.act(FakeKind, "set_tag", [choice.id], ctx)
    return ctx, ids


def seen_by(record: dict):
    def run(founds, ctx):
        record.update({found.entity.title: found.tags for found in founds})
        return []

    return run


@pytest.mark.parametrize("title, tags", [("Ubik", ("scifi",)), ("Dune", ())])
def test_a_kind_verb_sees_each_entitys_tags(tagged_shelf, title, tags):
    ctx, ids = tagged_shelf
    record = {}
    kind = FakeKind._replace(verbs={"peek": Verb("Peek", seen_by(record))})
    api.act(kind, "peek", [ids["dune"], ids["ubik"]], ctx)
    assert record[title] == tags, f"a verb should see {title} tagged {tags}"


def test_lint_sees_each_entitys_tags(tagged_shelf):
    ctx, _ = tagged_shelf
    record = {}

    def lint(founds, ctx):
        record.update({found.entity.title: found.tags for found in founds})
        return Plan()

    api.plan(FakeKind._replace(lint=lint), "", ctx)
    assert record == {"Dune": (), "Ubik": ("scifi",)}, "lint should see every entity's tags"


def test_a_found_built_without_tags_has_none():
    from hoard.contract import Entity, Found

    assert Found(Entity("id", "Dune"), ()).tags == (), "tags should default to empty for kinds and tests that build a Found"
