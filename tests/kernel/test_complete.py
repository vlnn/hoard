from __future__ import annotations

import pytest

from hoard import api
from hoard.render import text
from hoard.testing import FakeKind
from hoard.testing.fake import write_note

COMPLETES = "↩ to complete"


@pytest.fixture
def library(ctx, shelf):
    write_note(shelf, "dune", "Dune", "Frank Herbert", "1965", mtime=3000)
    write_note(shelf, "upgrade", "Upgrade", "Blake Crouch", "2022", mtime=2000)
    api.update(FakeKind, ctx)
    return ctx


@pytest.fixture
def tagging(context_with, shelf, satchel):
    shelf.mkdir()
    satchel.mkdir()
    write_note(shelf, "dune", "Dune", "Frank Herbert", "1965", mtime=3000)
    ctx = context_with(fake_shelf=str(shelf), fake_satchel=str(satchel), fake_tags="scifi")
    api.update(FakeKind, ctx)
    return ctx


def lines(ctx, typed):
    return text.render(api.filter(FakeKind, typed, ctx))


def completions(ctx, typed):
    return [line for line in lines(ctx, typed) if line.endswith(COMPLETES)]


@pytest.mark.parametrize(
    "typed, expected",
    [
        ("up", ["» fk update | ↩ to complete"]),
        ("upd", ["» fk update | ↩ to complete"]),
        ("UP", ["» fk update | ↩ to complete"]),
        ("st", ["» fk stats | ↩ to complete"]),
        ("un", ["» fk undo | ↩ to complete"]),
        ("lo", ["» fk loose | ↩ to complete"]),
    ],
)
def test_a_partial_command_word_is_offered_first(library, typed, expected):
    assert lines(library, typed)[: len(expected)] == expected, f"fk {typed} should first offer to complete it to {expected}"


def test_books_matching_the_partial_word_follow_its_completion(library):
    assert lines(library, "up")[1].startswith("Upgrade"), "a book whose title starts with the typed word should still be found"


def test_a_completion_row_fills_the_query_instead_of_running(library):
    head = api.filter(FakeKind, "up", library).rows[0]
    assert (head.verb, head.complete) == (None, "update "), "↩ on a completion row should extend the query, not run a verb"


@pytest.mark.parametrize("typed", ["", "u", "update", "up ", " up", "up dune", "zz", "loose"])
def test_nothing_is_offered_once_the_first_word_is_settled(library, typed):
    assert completions(library, typed) == [], f"fk {typed!r} should not offer completions"


def test_a_partial_command_word_is_offered_on_an_empty_index(ctx):
    assert lines(ctx, "up")[0] == "» fk update | ↩ to complete", "a fresh index should still complete update"


@pytest.mark.parametrize("typed, command", [("mo", "model"), ("ta", "tag"), ("li", "like"), ("na", "name")])
def test_a_command_the_context_does_not_offer_is_not_completed(library, typed, command):
    assert completions(library, typed) == [], f"fk {typed} should not offer {command} when it is not configured"


def test_a_command_the_context_offers_is_completed(tagging):
    assert completions(tagging, "ta") == ["» fk tag | ↩ to complete"], "fk ta should offer tag once tags are configured"
