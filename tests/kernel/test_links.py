from __future__ import annotations

import pytest

from hoard import api
from hoard.contract import TAGS, ContractError, Kind, LocalVectors, Standard, Standardize, Verb
from hoard.items import Item
from hoard.render import text
from hoard.testing import FakeKind
from hoard.testing.fake import write_note

LATIN, CYRILLIC, INITIALS, FULL = "Zelazny, Roger", "Желязни, Роджер", "R. Zelazny", "Roger Zelazny"
LINK = Standard(LATIN, (CYRILLIC,), search_only=True)
MERGE = Standard(LATIN, (INITIALS,))
RENAME = Standard(FULL, (LATIN,))
ACCEPT_ALL = "» Accept 1 | ↩ makes every spelling below standard"


def proposing(*standards):
    return lambda spellings, ctx: list(standards)


seen = {}


def peek(founds, ctx):
    seen["ctx"] = ctx
    return []


def kind_with(*standards, tags=()):
    records = {"author": Standardize(proposing(*standards), "; ")}
    if tags:
        records[TAGS] = Standardize(proposing(*tags))
    verbs = {**FakeKind.verbs, "peek": Verb("Peek", peek)}
    return Kind(**{**FakeKind._asdict(), "standards": records, "verbs": verbs})


KIND = kind_with(LINK)


@pytest.fixture
def notes(context_with, shelf, satchel):
    shelf.mkdir()
    satchel.mkdir()
    ctx = context_with(fake_shelf=str(shelf), fake_satchel=str(satchel), fake_tags="scifi")
    write_note(shelf, "lord", "Lord of Light", LATIN, "1967", mtime=3000)
    write_note(shelf, "amber", "Nine Princes in Amber", f"{LATIN}; Jane Lindskold", "1970", mtime=2500)
    write_note(shelf, "knyaz", "Девять принцев Амбера", CYRILLIC, "1992", mtime=2000)
    write_note(shelf, "dune", "Dune", "Frank Herbert", "1965", mtime=1000)
    api.update(KIND, ctx)
    return ctx


def lines(ctx, typed, kind=KIND):
    return text.render(api.filter(kind, typed, ctx))


def titles(ctx, typed, kind=KIND):
    return [row.title for row in api.filter(kind, typed, ctx).rows if isinstance(row, Item)]


def rows(ctx, typed, kind=KIND):
    return [row for row in api.filter(kind, typed, ctx).rows if isinstance(row, Item)]


def entity_id(ctx, title):
    return next(row.id for row in rows(ctx, title.split()[0].lower()) if row.title == title)


def accept(ctx, kind=KIND):
    return api.act(kind, "standardize", ["std:"], ctx)


def test_a_search_only_standard_cannot_be_trivial():
    with pytest.raises(ContractError, match="search-only standard cannot be trivial"):
        Standard("a", ("b",), trivial=True, search_only=True)


def test_a_search_only_standard_joins_exactly_two_spellings():
    with pytest.raises(ContractError, match="exactly two spellings"):
        Standard("a", ("b", "c"), search_only=True)


def test_a_link_proposed_the_other_way_round_is_the_same_proposal(notes):
    key = rows(notes, "std")[0].id
    api.update(kind_with(Standard(CYRILLIC, (LATIN,), search_only=True)), notes)
    assert rows(notes, "std")[0].id == key, "a pair has one key whichever side the kind names first"


def test_a_standard_is_not_search_only_unless_told():
    assert Standard("a", ("b",)).search_only is False, "a plain standard merges spellings"


def test_a_link_waits_in_std_as_a_pair(notes):
    assert lines(notes, "std") == [ACCEPT_ALL, f"{LATIN} ↔ {CYRILLIC} | author · link · 3 notes"], (
        "a search-only standard should read as a symmetric pair with the books on both sides"
    )
    assert rows(notes, "std")[0].verb == "link", "↩ on the row links"


def test_a_link_makes_either_spelling_find_both_sides(notes):
    assert api.act(KIND, "link", [rows(notes, "std")[0].id], notes) == f"Linked: {LATIN} ↔ {CYRILLIC}", "say what was linked"
    assert titles(notes, "желязни") == ["Lord of Light", "Nine Princes in Amber", "Девять принцев Амбера"], "Cyrillic finds Latin"
    assert titles(notes, "zelazny") == ["Lord of Light", "Nine Princes in Amber", "Девять принцев Амбера"], "Latin finds Cyrillic"
    assert titles(notes, "roger") == ["Lord of Light", "Nine Princes in Amber", "Девять принцев Амбера"], "a given name works too"
    assert titles(notes, "herbert") == ["Dune"], "unlinked spellings are untouched"


def test_a_link_changes_no_field(notes):
    accept(notes)
    assert lines(notes, "девять")[0].startswith(f"Девять принцев Амбера | shelf · {CYRILLIC} · 1992"), "the book keeps its own spelling"
    assert lines(notes, "lord")[0].startswith(f"Lord of Light | shelf · {LATIN} · 1967"), "and so does the other side"
    assert lines(notes, "std") == ["» Nothing to standardize"], "an accepted link should leave the list"


def test_kind_code_sees_a_link_through_the_context_but_not_as_a_standard(notes):
    accept(notes)
    api.act(KIND, "peek", [entity_id(notes, "Lord of Light")], notes)
    assert seen["ctx"].linked("author", LATIN) == CYRILLIC, "a verb should see the partner of a linked spelling"
    assert seen["ctx"].linked("author", CYRILLIC) == LATIN, "in both directions"
    assert seen["ctx"].linked("author", "Frank Herbert") is None, "an unlinked spelling has no partner"
    assert seen["ctx"].standard("author", CYRILLIC) == CYRILLIC, "a link is not a standard"


def test_a_link_narrows_a_command_list_too(notes):
    accept(notes)
    assert titles(notes, "loose желязни") == ["Lord of Light", "Nine Princes in Amber", "Девять принцев Амбера"], (
        "words after a command should match linked spellings like a plain search"
    )


def test_a_link_survives_a_tag_change_and_a_full_reread(notes):
    accept(notes)
    choice = next(row for row in rows(notes, f"tag #{entity_id(notes, 'Lord of Light')} scifi") if row.title == "scifi")
    api.act(KIND, "set_tag", [choice.id], notes)
    assert "Lord of Light" in titles(notes, "желязни"), "tagging rebuilds the search text with the link still in it"
    api.update(KIND, notes, full=True)
    assert "Девять принцев Амбера" in titles(notes, "zelazny"), "a full reread keeps the link"


def test_undoing_a_link_takes_the_match_away_and_brings_the_proposal_back(notes):
    accept(notes)
    assert api.act(KIND, "undo", [], notes) == "Undid Standardize", "linking should undo"
    assert titles(notes, "желязни") == ["Девять принцев Амбера"], "the Latin books should no longer match"
    assert titles(notes, "zelazny") == ["Lord of Light", "Nine Princes in Amber"], "nor the Cyrillic one"
    assert lines(notes, "std")[1].startswith(f"{LATIN} ↔ {CYRILLIC}"), "the proposal should wait again"


def test_keeping_a_pair_apart_drops_the_link_for_good(notes):
    assert api.act(KIND, "keep_apart", [rows(notes, "std")[0].id], notes) == f"Kept apart: {CYRILLIC}", "say what was kept"
    api.update(KIND, notes)
    assert lines(notes, "std") == ["» Nothing to standardize"], "a pair kept apart should not be proposed again"
    assert titles(notes, "zelazny") == ["Lord of Light", "Nine Princes in Amber"], "nothing should have been linked"


def test_the_picker_offers_link_and_keep_apart(notes):
    key = rows(notes, "std")[0].id[len("std#") :]
    assert lines(notes, f"std #{key}") == [
        f"» author: {LATIN} ↔ {CYRILLIC} | a link has no standard spelling",
        "Link | either spelling finds the notes of both",
        "Keep apart | these stay different spellings",
    ], "a link has no spelling to pick"
    link = rows(notes, f"std #{key}")[0]
    assert api.act(KIND, "link", [link.id], notes) == f"Linked: {LATIN} ↔ {CYRILLIC}", "↩ on Link links"


def test_a_linked_spelling_is_not_offered_another_link(notes, shelf):
    accept(notes)
    kind = kind_with(LINK, Standard(LATIN, ("Зелазни, Роджер",), search_only=True))
    write_note(shelf, "jack", "Валет из Страны Теней", "Зелазни, Роджер", "1994", mtime=500)
    api.update(kind, notes)
    assert lines(notes, "std", kind) == ["» Nothing to standardize"], "one link per spelling; merge the Cyrillic variants first"


def test_a_link_needs_books_on_both_sides(ctx, shelf):
    write_note(shelf, "lord", "Lord of Light", LATIN, "1967")
    api.update(KIND, ctx)
    assert lines(ctx, "std") == ["» Nothing to standardize"], "a link to a spelling no book carries is not offered"


def test_a_later_merge_carries_the_link_to_the_new_standard(notes, shelf):
    accept(notes)
    kind = kind_with(LINK, RENAME)
    write_note(shelf, "roadmarks", "Roadmarks", FULL, "1979", mtime=500)
    api.update(kind, notes)
    assert lines(notes, "std", kind) == [ACCEPT_ALL, f"{FULL} | author · {LATIN} · 2 notes"], "only the merge should wait"
    accept(notes, kind)
    assert titles(notes, "желязни", kind) == ["Lord of Light", "Nine Princes in Amber", "Девять принцев Амбера", "Roadmarks"], (
        "the Cyrillic spelling should now find every book under the new standard"
    )
    assert titles(notes, "roadmarks желязни", kind) == ["Roadmarks"], "including one that never carried the old spelling"
    assert titles(notes, "roger", kind) == ["Lord of Light", "Nine Princes in Amber", "Девять принцев Амбера", "Roadmarks"], (
        "and the new standard should find the Cyrillic book"
    )


def test_a_link_proposed_on_a_variant_binds_the_standard(notes, shelf):
    write_note(shelf, "roadmarks", "Roadmarks", FULL, "1979", mtime=500)
    api.update(kind_with(RENAME), notes)
    accept(notes, kind_with(RENAME))
    kind = kind_with(RENAME, LINK)
    api.update(kind, notes)
    assert lines(notes, "std", kind) == [ACCEPT_ALL, f"{FULL} ↔ {CYRILLIC} | author · link · 4 notes"], (
        "a link offered for a spelling that has a standard should be offered for the standard"
    )


def test_a_merge_into_a_linked_standard_keeps_the_link(notes, shelf):
    accept(notes)
    kind = kind_with(LINK, MERGE)
    write_note(shelf, "jack", "Jack of Shadows", INITIALS, "1971", mtime=500)
    api.update(kind, notes)
    accept(notes, kind)
    assert lines(notes, "jack", kind)[0].startswith(f"Jack of Shadows | shelf · {LATIN}"), "the merge should apply"
    assert "Jack of Shadows" in titles(notes, "желязни", kind), "the linked spelling should reach the merged book"
    assert "Девять принцев Амбера" in titles(notes, "zelazny", kind), "and the link should still hold the other way"


def test_a_tag_link_works_the_same_way(context_with, shelf, satchel):
    shelf.mkdir()
    satchel.mkdir()
    kind = kind_with(tags=(Standard("scifi", ("фантастика",), search_only=True),))
    ctx = context_with(fake_shelf=str(shelf), fake_satchel=str(satchel), fake_tags="scifi\nфантастика")
    write_note(shelf, "lord", "Lord of Light", LATIN, "1967", mtime=2000)
    write_note(shelf, "knyaz", "Девять принцев Амбера", CYRILLIC, "1992", mtime=1000)
    api.update(kind, ctx)
    for title, tag in (("Lord of Light", "scifi"), ("Девять принцев Амбера", "фантастика")):
        choice = next(row for row in rows(ctx, f"tag #{entity_id(ctx, title)} {tag}", kind) if row.title == tag)
        api.act(kind, "set_tag", [choice.id], ctx)
    api.update(kind, ctx)
    assert lines(ctx, "std", kind) == [ACCEPT_ALL, "scifi ↔ фантастика | tags · link · 2 notes"], "tags can be linked too"
    accept(ctx, kind)
    assert titles(ctx, "фантастика", kind) == ["Lord of Light", "Девять принцев Амбера"], "either tag finds both"
    assert lines(ctx, "lord", kind)[0].startswith("Lord of Light | shelf"), "the tag itself is unchanged"


def test_linking_and_unlinking_remake_the_vectors_of_the_books_concerned(notes, mocker):
    vector = mocker.Mock(side_effect=lambda found, ctx: [1.0, 0.0])
    kind = Kind(**{**KIND._asdict(), "like": LocalVectors("authors", vector)})
    api.update(kind, notes)
    vector.reset_mock()
    accept(notes, kind)
    api.update(kind, notes)
    assert sorted(call.args[0].entity.title for call in vector.call_args_list) == [
        "Lord of Light",
        "Nine Princes in Amber",
        "Девять принцев Амбера",
    ], "the holders of both spellings should get a new vector, Dune should not"
    vector.reset_mock()
    api.act(kind, "undo", [], notes)
    api.update(kind, notes)
    assert vector.call_count == 3, "undoing the link should remake the same vectors"
