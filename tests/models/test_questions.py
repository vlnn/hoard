from __future__ import annotations

import pytest

from hoard import _questions
from hoard.contract import Context
from hoard.testing import FakeKind

CTX = Context(data="", cache="", config={"fake_tags": "scifi\nfantasy"})


def test_the_name_schema_asks_for_title_nameable_fields_and_confidence():
    assert _questions.schema(FakeKind, CTX, "name") == {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "author": {"type": "string"},
            "year": {"type": "string"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": ["title", "author", "year", "confidence"],
    }, "name should ask for the title and every field the kind lets the model correct"


def test_the_tag_schema_is_an_enum_over_the_kinds_tags():
    assert _questions.schema(FakeKind, CTX, "tag")["properties"]["tag"] == {"type": "string", "enum": ["scifi", "fantasy"]}, (
        "tag should only allow the kind's own tags"
    )


@pytest.mark.parametrize(
    "kind, config, enabled",
    [
        (FakeKind, {"fake_tags": "scifi"}, ["name", "tag"]),
        (FakeKind, {}, ["name"]),
        (FakeKind._replace(nameable=()), {"fake_tags": "scifi"}, ["tag"]),
        (FakeKind._replace(nameable=(), tags=None), {}, []),
    ],
)
def test_questions_are_asked_only_when_the_kind_can_answer_them(kind, config, enabled):
    assert _questions.enabled(kind, Context(data="", cache="", config=config)) == enabled, (
        "a question needs nameable fields or a tag list"
    )


def test_questions_speak_of_the_kinds_noun():
    assert "this note" in _questions.text(FakeKind, "tag"), "the question should use the kind's label"
