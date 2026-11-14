from __future__ import annotations

import pytest

from hoard import _answers, _ask, api
from hoard.contract import Suggestion
from hoard.render import text
from hoard.testing import FakeKind
from hoard.testing.fake import read_note, write_note

TAGS = {"fake_tags": "scifi\nfantasy"}


def by_author(founds, ctx):
    return [Suggestion(f.entity.id, "scifi", 0.8, "rule") for f in founds if f.entity.fields[0] == "Philip K. Dick" and not f.tags]


def remember(log):
    return lambda found, change, ctx: log.append((found.entity.title, change.before, change.after))


def suggesting(kind, suggest=by_author, tagged=None):
    return kind._replace(suggest=suggest, tagged=tagged)


@pytest.fixture
def notes(context_with, shelf, satchel):
    shelf.mkdir()
    satchel.mkdir()
    ctx = context_with(fake_shelf=str(shelf), fake_satchel=str(satchel), **TAGS)
    ids = {
        "dune": read_note(write_note(shelf, "dune", "Dune", "Frank Herbert", "1965", mtime=2000)).id,
        "ubik": read_note(write_note(shelf, "ubik", "Ubik", "Philip K. Dick", "1969", mtime=1000)).id,
    }
    return ctx, ids


def lines(kind, ctx, typed):
    return text.render(api.filter(kind, typed, ctx))


def test_update_stores_the_kinds_suggestions_as_answers(notes):
    ctx, ids = notes
    kind = suggesting(FakeKind)
    api.update(kind, ctx)
    assert lines(kind, ctx, "tag ubik")[-1].startswith("Ubik | scifi? 80% · "), "the kind's suggestion should show like the model's"
    assert lines(kind, ctx, "tag dune")[-1].startswith("Dune | shelf"), "a book the kind did not suggest for stays plain"


def test_suggestions_are_accepted_together(notes):
    ctx, ids = notes
    kind = suggesting(FakeKind)
    api.update(kind, ctx)
    assert "» Accept 1 suggested | scifi 1" in lines(kind, ctx, "tag"), "suggestions should be offered as one batch"
    assert api.act(kind, "accept_tags", ["suggested:"], ctx) == "Tagged Ubik: scifi", "accepting should tag the book"
    assert lines(kind, ctx, "scifi")[0].startswith("Ubik |"), "the tag should be searchable like any other"


def test_a_kind_suggestion_leaves_the_book_stale_for_the_model(notes):
    ctx, ids = notes
    kind = suggesting(FakeKind)
    api.update(kind, ctx)
    con = api.open_database(kind, api.context(kind, ctx))
    assert [i for i, _ in _answers.stale(con, "tag")] == [ids["dune"], ids["ubik"]], "a rule's guess should not count as the model's answer"
    con.close()


def test_a_fresh_model_answer_is_not_overwritten_by_a_suggestion(notes, mocker):
    ctx, ids = notes
    kind = suggesting(FakeKind)
    api.update(kind, ctx)
    con = api.open_database(kind, api.context(kind, ctx))
    (digest,) = con.execute("SELECT evidence_hash FROM entities WHERE id = ?", (ids["ubik"],)).fetchone()
    _answers.store(con, ids["ubik"], "tag", digest, "oracle", {"tag": "fantasy", "confidence": 0.9})
    con.commit()
    con.close()
    api.update(kind, ctx)
    assert lines(kind, ctx, "tag ubik")[-1].startswith("Ubik | fantasy? 90% · "), "the model's answer should win over the rule"


def test_the_picker_still_shows_a_kinds_guess_for_a_tagged_book(notes):
    ctx, ids = notes
    kind = suggesting(FakeKind, suggest=lambda founds, ctx: [Suggestion(f.entity.id, "fantasy", 0.8, "rule") for f in founds])
    api.update(kind, ctx)
    api.act(kind, "set_tag", [f'tagset:["#{ids["ubik"]}", "scifi"]'], ctx)
    api.update(kind, ctx)
    assert lines(kind, ctx, f"tag #{ids['ubik']}") == ["» Ubik | pick a tag", "fantasy | suggested · 80%", "scifi | current"], (
        "a tagged book keeps its tag; the picker offers the kind's guess first as it does the model's"
    )


def test_the_kind_hears_hand_picks_and_their_undo(notes):
    ctx, ids = notes
    log = []
    kind = suggesting(FakeKind, tagged=remember(log))
    api.update(kind, ctx)
    api.act(kind, "set_tag", [f'tagset:["#{ids["ubik"]}", "scifi"]'], ctx)
    assert log == [("Ubik", [], [["scifi", "hand"]])], "a hand pick should reach the kind with what changed"
    api.act(kind, "undo", [], ctx)
    assert log[-1] == ("Ubik", [["scifi", "hand"]], []), "undo should reach the kind with the change reversed"


def test_the_kind_hears_accepted_suggestions_too(notes):
    ctx, ids = notes
    log = []
    kind = suggesting(FakeKind, tagged=remember(log))
    api.update(kind, ctx)
    api.act(kind, "accept_tags", ["suggested:"], ctx)
    assert log == [("Ubik", [], [["scifi", "model"]])], "an accepted suggestion is set by the model side, not by hand"


def test_fold_carries_the_suggestion_on_found(notes):
    ctx, ids = notes
    kind = suggesting(FakeKind)
    api.update(kind, ctx)
    seen = {}
    kind = kind._replace(subtitle=lambda found, ctx: seen.setdefault(found.entity.title, found.suggested) or "")
    api.filter(kind, "", ctx)
    assert seen == {"Ubik": "scifi", "Dune": None}, "Found.suggested should carry the fresh guess, or None"
