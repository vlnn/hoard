from __future__ import annotations

import json

import pytest

from hoard import api
from hoard.contract import TAGS, ContractError, Kind, Spelling, Standard, Standardize, Verb
from hoard.items import Item
from hoard.render import text
from hoard.testing import FakeKind
from hoard.testing.fake import write_note

TRIVIAL = Standard("Philip K. Dick", ("philip k. dick",), trivial=True)
INITIALS = Standard("Philip K. Dick", ("P. K. Dick",))
SCIFI = Standard("scifi", ("sci-fi", "SF"))

seen = {}


def peek(founds, ctx):
    seen["ctx"] = ctx
    return []


def proposing(subject, standards):
    def propose(spellings, ctx):
        seen[subject] = {spelling.value: spelling.count for spelling in spellings}
        return list(standards)

    return propose


def kind_with(authors=(TRIVIAL, INITIALS), tags=(SCIFI,)):
    standards = {"author": Standardize(proposing("author", authors), "; "), TAGS: Standardize(proposing(TAGS, tags))}
    verbs = {**FakeKind.verbs, "peek": Verb("Peek", peek)}
    return Kind(**{**FakeKind._asdict(), "standards": standards, "verbs": verbs})


KIND = kind_with()


@pytest.fixture
def notes(ctx, shelf):
    write_note(shelf, "ubik", "Ubik", "Philip K. Dick", "1969", mtime=3000)
    write_note(shelf, "valis", "Valis", "philip k. dick", "1981", mtime=2000)
    write_note(shelf, "scanner", "A Scanner Darkly", "P. K. Dick; Ursula K. Le Guin", "1977", mtime=1000)
    api.update(KIND, ctx)
    return ctx


@pytest.fixture
def tagged_notes(context_with, shelf, satchel):
    shelf.mkdir()
    satchel.mkdir()
    ctx = context_with(fake_shelf=str(shelf), fake_satchel=str(satchel), fake_tags="scifi\nsci-fi\nfantasy")
    write_note(shelf, "ubik", "Ubik", "Philip K. Dick", "1969", mtime=3000)
    write_note(shelf, "dune", "Dune", "Frank Herbert", "1965", mtime=2000)
    api.update(KIND, ctx)
    return ctx


def lines(ctx, typed, kind=KIND):
    return text.render(api.filter(kind, typed, ctx))


def first(ctx, typed):
    return lines(ctx, typed)[0]


def rows(ctx, typed):
    return [row for row in api.filter(KIND, typed, ctx).rows if isinstance(row, Item)]


def rows_of(ctx, kind, typed):
    return [row for row in api.filter(kind, typed, ctx).rows if isinstance(row, Item)]


def entity_id(ctx, title):
    return next(row.id for row in rows(ctx, title.lower()) if row.title == title)


def tag(ctx, title, value):
    choice = next(row for row in rows(ctx, f"tag #{entity_id(ctx, title)} {value}") if row.title in (value, f"New tag: {value}"))
    return api.act(KIND, "set_tag", [choice.id], ctx)


@pytest.mark.parametrize(
    ("standards", "problem"),
    [
        ({"nope": Standardize(lambda s, c: [])}, "standards should name the kind's fields or tags"),
        ({"author": "not a record"}, "standards should be Standardize records"),
        ({"author": Standardize("not callable")}, "standards should be Standardize records"),
    ],
)
def test_a_kind_with_wrong_standards_refuses_to_build(standards, problem):
    with pytest.raises(ContractError, match=problem):
        Kind(**{**FakeKind._asdict(), "standards": standards})


def test_standard_tags_need_tags():
    with pytest.raises(ContractError, match="standard tags need tags"):
        Kind(**{**FakeKind._asdict(), "tags": None, "standards": {TAGS: Standardize(lambda s, c: [])}})


def test_std_belongs_to_the_kernel():
    with pytest.raises(ContractError, match="belong to the kernel"):
        Kind(**{**FakeKind._asdict(), "commands": {"std": FakeKind.commands["loose"]}})


def test_the_kind_is_shown_every_spelling_once_with_its_count(notes):
    assert seen["author"] == {"Philip K. Dick": 1, "philip k. dick": 1, "P. K. Dick": 1, "Ursula K. Le Guin": 1}, (
        "multi-valued fields should be split by the separator and counted per entity"
    )


def test_a_trivial_standard_applies_on_update(notes):
    assert first(notes, "valis").startswith("Valis | shelf · Philip K. Dick · 1981"), "a trivial variant should be rewritten"
    assert first(notes, "undo").startswith("» Undo Standardize"), "the automatic fix should be one undoable batch"


def test_other_standards_wait_in_std(notes):
    assert lines(notes, "std") == [
        "» Accept 1 | ↩ makes every spelling below standard",
        "Philip K. Dick | author · P. K. Dick · 1 note",
    ], "a standard that is not trivial should wait for accept"


def test_accepting_a_standard_rewrites_every_entity_using_the_variant(notes):
    assert api.act(KIND, "standardize", [rows(notes, "std")[0].id], notes) == "Standard: Philip K. Dick", "one standard"
    assert first(notes, "scanner").startswith("A Scanner Darkly | shelf · Philip K. Dick; Ursula K. Le Guin · 1977"), (
        "only the matching value in a multi-valued field should change"
    )
    assert lines(notes, "std") == ["» Nothing to standardize"], "an accepted standard should leave the list"


def test_accept_all_applies_every_listed_standard(notes):
    assert api.act(KIND, "standardize", ["std:"], notes) == "Standard: Philip K. Dick", "the head row applies the list"
    assert lines(notes, "std") == ["» Nothing to standardize"], "nothing should be left"


def test_undoing_an_accept_brings_the_variant_and_the_proposal_back(notes):
    api.act(KIND, "standardize", ["std:"], notes)
    assert api.act(KIND, "undo", [], notes) == "Undid Standardize", "accepting should undo"
    assert first(notes, "scanner").startswith("A Scanner Darkly | shelf · P. K. Dick; "), "the variant should be back"
    assert lines(notes, "std")[1].startswith("Philip K. Dick | author · P. K. Dick"), "the proposal should wait again"


def test_a_standard_survives_a_full_reread(notes):
    api.act(KIND, "standardize", ["std:"], notes)
    api.update(KIND, notes, full=True)
    assert first(notes, "scanner").startswith("A Scanner Darkly | shelf · Philip K. Dick; "), "a standard should stick"


def test_a_new_entity_with_a_known_variant_arrives_standardized(notes, shelf):
    api.act(KIND, "standardize", ["std:"], notes)
    write_note(shelf, "radio", "Radio Free Albemuth", "P. K. Dick", "1985", mtime=500)
    api.update(KIND, notes)
    assert first(notes, "albemuth").startswith("Radio Free Albemuth | shelf · Philip K. Dick · 1985"), "known variants map"


def test_keeping_apart_drops_the_proposal_for_good(notes):
    assert api.act(KIND, "keep_apart", [rows(notes, "std")[0].id], notes) == "Kept apart: P. K. Dick", "say what was kept"
    api.update(KIND, notes)
    assert lines(notes, "std") == ["» Nothing to standardize"], "a spelling kept apart should not be proposed again"
    assert first(notes, "scanner").startswith("A Scanner Darkly | shelf · P. K. Dick; "), "the spelling should stay"


def test_undoing_an_automatic_standard_keeps_its_spellings_apart(notes):
    api.act(KIND, "undo", [], notes)
    api.update(KIND, notes)
    assert first(notes, "valis").startswith("Valis | shelf · philip k. dick · 1981"), "undo should mean no, not later"


def test_the_picker_offers_each_spelling_and_keep_apart(notes):
    number = rows(notes, "std")[0].id[len("std#") :]
    assert lines(notes, f"std #{number}") == [
        "» author: Philip K. Dick | pick the standard spelling",
        "Philip K. Dick | current standard",
        "P. K. Dick",
        "Keep apart | these stay different spellings",
    ], "the picker should list the group"


def test_choosing_another_spelling_makes_it_the_standard_for_the_whole_chain(notes):
    number = rows(notes, "std")[0].id[len("std#") :]
    choice = next(row for row in rows(notes, f"std #{number}") if row.title == "P. K. Dick")
    assert api.act(KIND, "standardize", [choice.id], notes) == "Standard: P. K. Dick", "the chosen spelling wins"
    assert first(notes, "valis").startswith("Valis | shelf · P. K. Dick · 1981"), "earlier variants should follow"
    assert first(notes, "ubik").startswith("Ubik | shelf · P. K. Dick · 1969"), "the old standard should follow"


def test_command_return_on_a_proposal_reopens_the_picker(notes, mocker):
    run = mocker.patch("subprocess.run")
    proposal = rows(notes, "std")[0]
    assert [(mod.key, mod.verb) for mod in proposal.mods] == [("cmd", "pick_standard")], "⌘↩ should choose"
    assert api.act(KIND, "pick_standard", [proposal.id], notes) == "", "the picker reopens Alfred silently"
    assert f'search "fk std #{proposal.id[len("std#") :]} "' in run.call_args.args[0][-1], "Alfred should reopen"


def test_kind_code_sees_the_standards_through_the_context(notes):
    api.act(KIND, "standardize", ["std:"], notes)
    api.act(KIND, "peek", [entity_id(notes, "Ubik")], notes)
    assert seen["ctx"].standard("author", "P. K. Dick") == "Philip K. Dick", "verbs should map through the standards"
    assert seen["ctx"].standard("author", "Frank Herbert") == "Frank Herbert", "unknown values map to themselves"


def test_a_kind_without_standards_has_no_std_command(notes):
    assert lines(notes, "std", FakeKind) == ["» No match for std"], "std should stay a search word"


def test_tag_spellings_count_tagged_entities_and_include_the_kinds_tags(tagged_notes):
    tag(tagged_notes, "Ubik", "sci-fi")
    api.update(KIND, tagged_notes)
    assert seen[TAGS] == {"scifi": 0, "sci-fi": 1, "fantasy": 0}, "tags should be counted by use"


def test_accepting_a_tag_standard_retags_and_narrows_the_picker(tagged_notes):
    tag(tagged_notes, "Ubik", "sci-fi")
    api.update(KIND, tagged_notes)
    assert lines(tagged_notes, "std") == ["» Accept 1 | ↩ makes every spelling below standard", "scifi | tags · sci-fi · 1 note"]
    api.act(KIND, "standardize", ["std:"], tagged_notes)
    assert first(tagged_notes, "scifi").startswith("Ubik | "), "the entity should carry the standard tag"
    assert [line for line in lines(tagged_notes, f"tag #{entity_id(tagged_notes, 'Dune')}")[1:] if not line.startswith("New")] == [
        "scifi",
        "fantasy",
    ], "the picker should not offer a variant"


def test_a_variant_tag_set_by_hand_is_stored_as_the_standard(tagged_notes):
    tag(tagged_notes, "Ubik", "sci-fi")
    api.update(KIND, tagged_notes)
    api.act(KIND, "standardize", ["std:"], tagged_notes)
    assert tag(tagged_notes, "Dune", "SF") == "Tagged Dune: scifi", "a variant typed by hand should become the standard"


def test_a_models_guess_shows_as_its_standard(tagged_notes, replies):
    tagged_notes = tagged_notes._replace(config={**tagged_notes.config, "hoard_chat_url": "http://m:8080"})
    reply = {"choices": [{"message": {"content": json.dumps({"tag": "sci-fi", "confidence": 0.9})}}]}
    replies(reply, reply)
    api.ask(KIND, tagged_notes, ["tag"])
    tag(tagged_notes, "Ubik", "sci-fi")
    api.update(KIND, tagged_notes)
    api.act(KIND, "standardize", ["std:"], tagged_notes)
    assert any(line.startswith("Dune | scifi? 90%") for line in lines(tagged_notes, "tag")), "guesses should be mapped"


def test_spelling_and_standard_records_have_sensible_defaults():
    assert Spelling("x") == Spelling("x", 0), "a spelling counts zero entities unless told"
    assert Standard("a", ("b",)).trivial is False, "a standard waits for accept unless marked trivial"
    assert Standardize(len).separator == "", "a field is single-valued unless a separator is given"


def test_undoing_a_tag_standard_restores_the_variant_tag(tagged_notes):
    tag(tagged_notes, "Ubik", "sci-fi")
    api.update(KIND, tagged_notes)
    api.act(KIND, "standardize", ["std:"], tagged_notes)
    api.act(KIND, "undo", [], tagged_notes)
    assert first(tagged_notes, "sci fi").startswith("Ubik | "), "undo should put the variant tag back"
    assert "sci-fi" in lines(tagged_notes, f"tag #{entity_id(tagged_notes, 'Dune')}"), "the picker should offer it again"


def test_a_proposer_that_raises_leaves_the_update_alone(ctx, shelf, capsys):
    def broken(spellings, ctx):
        raise ValueError("no rules today")

    kind = Kind(**{**FakeKind._asdict(), "standards": {"author": Standardize(broken)}})
    write_note(shelf, "ubik", "Ubik", "Philip K. Dick", "1969")
    assert api.update(kind, ctx) == 1, "the update should still index"
    assert lines(ctx, "std", kind) == ["» Nothing to standardize"], "a failing proposer proposes nothing"
    assert "no rules today" in capsys.readouterr().err, "the error should reach the worker log"


def test_a_name_suggestion_that_a_standard_already_covers_is_not_offered(notes, replies):
    notes = notes._replace(config={**notes.config, "hoard_chat_url": "http://m:8080"})
    api.act(KIND, "standardize", ["std:"], notes)
    answer = {"title": "A Scanner Darkly", "author": "P. K. Dick; Ursula K. Le Guin", "year": "1977", "confidence": 0.5}
    same = {"choices": [{"message": {"content": json.dumps(answer)}}]}
    other = {"choices": [{"message": {"content": json.dumps({"confidence": 0.1})}}]}
    replies(other, other, same)
    api.ask(KIND, notes, ["name"])
    assert not any(line.startswith("A Scanner Darkly") for line in lines(notes, "name")), (
        "a suggestion that only restores a variant spelling should not be offered"
    )


LE_GUIN = Standard("Ursula K. Le Guin", ("U. K. Le Guin",))


def picker_choice(ctx, kind, spelling):
    proposal = next(row for row in api.filter(kind, "std", ctx).rows if isinstance(row, Item) and spelling in row.subtitle)
    key = proposal.id[len("std#") :]
    return key, next(row for row in api.filter(kind, f"std #{key}", ctx).rows if isinstance(row, Item) and row.title == spelling)


def test_a_choice_still_means_its_own_group_after_an_update_adds_another(ctx, shelf):
    kind = kind_with(authors=(LE_GUIN, INITIALS))
    write_note(shelf, "scanner", "A Scanner Darkly", "P. K. Dick; Philip K. Dick", "1977")
    api.update(kind, ctx)
    _, choice = picker_choice(ctx, kind, "P. K. Dick")
    write_note(shelf, "lathe", "The Lathe of Heaven", "U. K. Le Guin; Ursula K. Le Guin", "1971")
    api.update(kind, ctx)
    assert api.act(kind, "standardize", [choice.id], ctx) == "Standard: P. K. Dick", "the choice should keep its meaning"
    assert first(ctx, "lathe").startswith("The Lathe of Heaven | shelf · U. K. Le Guin; Ursula K. Le Guin"), "others stay"


def test_a_choice_outside_its_group_is_refused(notes):
    key, _ = picker_choice(notes, KIND, "P. K. Dick")
    forged = "stdpick:" + json.dumps([key, "Frank Herbert"])
    assert api.act(KIND, "standardize", [forged], notes) == "Nothing to standardize", "only a spelling of the group can win"


def test_undo_brings_a_proposal_back_beside_the_others(ctx, shelf):
    kind = kind_with(authors=(LE_GUIN, INITIALS))
    write_note(shelf, "scanner", "A Scanner Darkly", "P. K. Dick; Philip K. Dick", "1977")
    write_note(shelf, "lathe", "The Lathe of Heaven", "U. K. Le Guin; Ursula K. Le Guin", "1971")
    api.update(kind, ctx)
    le_guin = next(row for row in rows_of(ctx, kind, "std") if row.title == "Ursula K. Le Guin")
    api.act(kind, "standardize", [le_guin.id], ctx)
    api.update(kind, ctx)
    api.act(kind, "undo", [], ctx)
    assert lines(ctx, "std", kind)[0] == "» Accept 2 | ↩ makes every spelling below standard", "both should wait again"


def test_choosing_another_standard_takes_the_proposal_off_the_list(notes):
    _, choice = picker_choice(notes, KIND, "P. K. Dick")
    api.act(KIND, "standardize", [choice.id], notes)
    assert lines(notes, "std") == ["» Nothing to standardize"], "the group is settled whichever spelling won"


def test_undo_restores_entities_indexed_while_the_standard_held(notes, shelf):
    api.act(KIND, "standardize", ["std:"], notes)
    write_note(shelf, "radio", "Radio Free Albemuth", "P. K. Dick", "1985", mtime=500)
    api.update(KIND, notes)
    api.act(KIND, "undo", [], notes)
    assert first(notes, "albemuth").startswith("Radio Free Albemuth | shelf · P. K. Dick · 1985"), "undo should reach it too"


def test_a_proposal_whose_standard_was_mapped_follows_the_map(tagged_notes):
    narrow = kind_with(tags=(Standard("scifi", ("sci-fi",)),))
    api.update(narrow, tagged_notes)
    _, choice = picker_choice(tagged_notes, narrow, "sci-fi")
    api.act(narrow, "standardize", [choice.id], tagged_notes)
    tag(tagged_notes, "Dune", "SF")
    api.update(KIND, tagged_notes)
    assert lines(tagged_notes, "std")[1:] == ["sci-fi | tags · SF · 1 note"], "the group should continue under the chosen standard"


@pytest.mark.parametrize(
    ("rules", "shown"),
    [
        ((Standard("b", ("a",), True), Standard("a", ("b",), True)), "b"),
        ((Standard("b", ("a",), True), Standard("c", ("b",), True)), "c"),
    ],
)
def test_overlapping_proposals_leave_no_cycles_or_chains(ctx, shelf, rules, shown):
    kind = kind_with(authors=rules, tags=())
    write_note(shelf, "one", "One", "a", mtime=2000)
    write_note(shelf, "two", "Two", "b", mtime=1000)
    api.update(kind, ctx)
    api.update(kind, ctx)
    assert [line.split(" · ")[1] for line in lines(ctx, "", kind)] == [shown, shown], "every spelling should reach the end"
    api.act(kind, "undo", [], ctx)
    assert lines(ctx, "undo", kind) == ["» Nothing to undo"], "a second update should find nothing more to fix"


def test_a_spelling_kept_apart_stays_apart_after_becoming_a_standard(notes, shelf):
    api.act(KIND, "keep_apart", [rows(notes, "std")[0].id], notes)
    kind = kind_with(authors=(TRIVIAL, INITIALS, Standard("P. K. Dick", ("PKD",))))
    write_note(shelf, "valis2", "Valis Two", "PKD", mtime=100)
    api.update(kind, notes)
    api.act(kind, "standardize", ["std:"], notes)
    api.update(kind, notes)
    assert lines(notes, "std", kind) == ["» Nothing to standardize"], "keeping apart should outlive later standards"


def test_tags_of_entities_no_longer_indexed_are_not_counted(tagged_notes, shelf):
    tag(tagged_notes, "Ubik", "sci-fi")
    (shelf / "ubik.note").unlink()
    api.update(KIND, tagged_notes)
    assert seen[TAGS]["sci-fi"] == 0, "a tag on a vanished entity should not count as use"


def test_a_full_update_reads_the_standards_once(notes, mocker):
    from hoard import _standards

    spy = mocker.spy(_standards, "mapping")
    api.update(KIND, notes, full=True)
    assert spy.call_count <= 3, "the map should be read once per update, not once per entity"
