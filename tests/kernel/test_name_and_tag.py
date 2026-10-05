from __future__ import annotations

import json

import pytest

from hoard import _db, api, cli
from hoard.render import text
from hoard.testing import FakeKind
from hoard.testing.fake import read_note, write_note

CHAT = {"hoard_chat_url": "http://m:8080", "fake_tags": "scifi\nfantasy"}


def chat_reply(answer: dict) -> dict:
    return {"choices": [{"message": {"content": json.dumps(answer)}}]}


def named(title, author, year, confidence):
    return chat_reply({"title": title, "author": author, "year": year, "confidence": confidence})


def tagged(tag, confidence=0.9):
    return chat_reply({"tag": tag, "confidence": confidence})


@pytest.fixture
def served(context_with, shelf, satchel):
    shelf.mkdir()
    satchel.mkdir()
    ctx = context_with(fake_shelf=str(shelf), fake_satchel=str(satchel), **CHAT)
    ids = {
        "dune": read_note(write_note(shelf, "dune", "dune", body="Dune by Frank Herbert, 1965", mtime=2000)).id,
        "ubik": read_note(write_note(shelf, "ubik", "Ubik", "Philip K. Dick", "1969", mtime=1000)).id,
    }
    api.update(FakeKind, ctx)
    return ctx, ids


def lines(ctx, typed):
    return text.render(api.filter(FakeKind, typed, ctx))


def test_a_confident_name_overlays_the_index_and_never_the_file(served, replies, shelf):
    ctx, ids = served
    replies(named("Dune", "Frank Herbert", "1965", 0.95), named("Ubik", "Philip K. Dick", "1969", 0.9))
    assert api.ask(FakeKind, ctx, ["name"]) == 2, "both notes should be answered"
    assert lines(ctx, "herbert")[0].startswith("Dune | shelf · Frank Herbert · 1965 · "), "the answer should be searchable"
    assert (shelf / "dune.note").read_text().startswith("title: dune\n"), "the file should never change"


def test_an_overlay_survives_a_reread(served, replies, shelf):
    ctx, ids = served
    replies(named("Dune", "Frank Herbert", "1965", 0.95), named("Ubik", "Philip K. Dick", "1969", 0.9))
    api.ask(FakeKind, ctx, ["name"])
    api.update(FakeKind, ctx, full=True)
    assert lines(ctx, "herbert")[0].startswith("Dune | "), "a confident answer should apply after every re-read"


def test_a_second_ask_sends_nothing_for_fresh_answers(served, replies):
    ctx, _ = served
    replies(named("Dune", "Frank Herbert", "1965", 0.95), named("Ubik", "Philip K. Dick", "1969", 0.9))
    api.ask(FakeKind, ctx, ["name"])
    urlopen = replies()
    assert api.ask(FakeKind, ctx, ["name"]) == 0, "fresh answers should not be asked again"
    urlopen.assert_not_called()


def test_every_exchange_is_kept_for_later(served, replies):
    ctx, _ = served
    replies(named("Dune", "Frank Herbert", "1965", 0.95), named("Ubik", "Philip K. Dick", "1969", 0.9))
    api.ask(FakeKind, ctx, ["name"])
    con = _db.connect(_db.path_for("fake", ctx.data))
    assert con.execute("SELECT count(*) FROM exchanges").fetchone() == (2,), "each call should be logged"
    con.close()


def test_an_unsure_name_waits_in_the_name_command(served, replies):
    ctx, ids = served
    replies(named("Dune", "Frank Herbert", "1965", 0.5), named("Ubik", "Philip K. Dick", "1969", 0.95))
    api.ask(FakeKind, ctx, ["name"])
    assert lines(ctx, "name") == [
        "» Accept 1 | ↩ accepts every suggestion below",
        "Dune | 50% · Frank Herbert · 1965 · was dune",
    ], "an unsure answer should be offered, not applied"


def test_accepting_a_name_applies_it_and_undo_restores_the_old_one(served, replies):
    ctx, ids = served
    replies(named("Dune", "Frank Herbert", "1965", 0.5), named("Ubik", "Philip K. Dick", "1969", 0.95))
    api.ask(FakeKind, ctx, ["name"])
    assert api.act(FakeKind, "accept", ["names:"], ctx) == "Accepted 1 name", "accept should count what it applied"
    assert lines(ctx, "dune")[0].startswith("Dune | shelf · Frank Herbert · 1965"), "the accepted name should show"
    assert lines(ctx, "name") == ["» Nothing to name"], "nothing should be left to accept"
    assert api.act(FakeKind, "undo", [], ctx) == "Undid Accept names", "accepting should undo"
    assert lines(ctx, "dune")[0].startswith("dune | shelf · "), "undo should bring the old title back"


def test_names_not_asked_yet_offer_an_ask_row(served):
    ctx, _ = served
    assert lines(ctx, "name") == ["» Ask about 2 notes | the model runs in the background"], (
        "unanswered entities should be offered to the model"
    )


def test_name_without_a_chat_server_is_a_search_word(served):
    ctx, _ = served
    plain = ctx._replace(config={key: value for key, value in ctx.config.items() if key != "hoard_chat_url"})
    assert not any(line.startswith("» ") for line in lines(plain, "name")), "no server means no name command"


def test_a_server_that_fails_stops_the_job_and_stores_nothing(served, replies):
    import urllib.error

    ctx, _ = served
    replies(urllib.error.URLError("refused"))
    with pytest.raises(api.ModelError):
        api.ask(FakeKind, ctx, ["name"])
    assert lines(ctx, "name")[0].startswith("» Ask about 2 notes"), "nothing should have been stored"


def test_tag_lists_untagged_entities_with_the_models_guess(served, replies, shelf):
    ctx, ids = served
    replies(tagged("scifi"), tagged("fantasy", 0.4))
    api.ask(FakeKind, ctx, ["tag"])
    assert lines(ctx, "tag") == [
        "» Accept 2 suggested | fantasy 1 · scifi 1",
        "» Tag all 2 | pick one tag for every row below",
        f"dune | scifi? 90% · shelf · {shelf}/dune.note",
        f"Ubik | fantasy? 40% · shelf · Philip K. Dick · 1969 · {shelf}/ubik.note",
    ], "the guess should lead each row, and the accept row should say which tags it applies"


def test_the_accept_row_tallies_the_most_common_guess_first(served, replies):
    ctx, _ = served
    replies(tagged("scifi"), tagged("scifi"))
    api.ask(FakeKind, ctx, ["tag"])
    assert lines(ctx, "tag")[0] == "» Accept 2 suggested | scifi 2", "identical guesses should be counted together"


def test_the_picker_puts_the_models_guess_first(served, replies):
    ctx, ids = served
    replies(tagged("scifi"), tagged("fantasy", 0.4))
    api.ask(FakeKind, ctx, ["tag"])
    assert lines(ctx, f"tag #{ids['ubik']}") == ["» Ubik | pick a tag", "fantasy | suggested · 40%", "scifi"], (
        "the guess should be the first choice, so ↩ ↩ accepts it"
    )


def test_return_on_a_tag_row_opens_the_picker(served, mocker):
    ctx, ids = served
    run = mocker.patch("subprocess.run")
    row = api.filter(FakeKind, "tag ubik", ctx).rows[-1]
    assert (row.verb, row.id) == ("pick", ids["ubik"]), "↩ should pick a tag for this row"
    assert api.act(FakeKind, "pick", [row.id], ctx) == "", "picking reopens Alfred and posts no notification"
    script = run.call_args.args[0][-1]
    assert f'search "fk tag #{ids["ubik"]} "' in script, "Alfred should reopen with the picker query"


def test_the_picker_lists_the_kinds_tags_and_free_text(served):
    ctx, ids = served
    assert lines(ctx, f"tag #{ids['ubik']}") == ["» Ubik | pick a tag", "scifi", "fantasy"], "every tag should be offered"
    assert lines(ctx, f"tag #{ids['ubik']} fan") == ["» Ubik | pick a tag", "fantasy", "New tag: fan"], (
        "typing should narrow the tags and offer the text as a new one"
    )


def test_picking_a_tag_tags_the_entity_and_undoes(served):
    ctx, ids = served
    choice = api.filter(FakeKind, f"tag #{ids['ubik']} scifi", ctx).rows[1]
    assert api.act(FakeKind, "set_tag", [choice.id], ctx) == "Tagged Ubik: scifi", "the notification should say so"
    assert lines(ctx, "scifi")[0].startswith("Ubik | "), "tags should be searchable"
    assert [line for line in lines(ctx, "tag") if "Ubik" in line] == [], "a tagged entity leaves the tag list"
    api.act(FakeKind, "undo", [], ctx)
    assert any("Ubik" in line for line in lines(ctx, "tag")), "undo should untag it"


def test_a_hand_tag_drops_the_models_guess(served, replies):
    ctx, ids = served
    replies(tagged("scifi"), tagged("fantasy"))
    api.ask(FakeKind, ctx, ["tag"])
    choice = api.filter(FakeKind, f"tag #{ids['ubik']} scifi", ctx).rows[1]
    api.act(FakeKind, "set_tag", [choice.id], ctx)
    con = _db.connect(_db.path_for("fake", ctx.data))
    assert con.execute("SELECT count(*) FROM answers WHERE id = ? AND question = 'tag'", (ids["ubik"],)).fetchone() == (0,), (
        "a hand tag should delete the model's answer"
    )
    con.close()


def test_accepting_suggested_tags_tags_them_all_in_one_batch(served, replies):
    ctx, _ = served
    replies(tagged("scifi"), tagged("fantasy"))
    api.ask(FakeKind, ctx, ["tag"])
    assert api.act(FakeKind, "accept_tags", ["suggested:"], ctx) == "Tagged 2 notes", "one batch should tag both"
    assert lines(ctx, "tag") == ["» Nothing to tag"], "nothing should be left untagged"
    api.act(FakeKind, "undo", [], ctx)
    assert len(lines(ctx, "tag")) == 4, "the batch should undo as one"


def test_tag_all_picks_one_tag_for_every_row(served):
    ctx, _ = served
    choice = api.filter(FakeKind, "tag #* scifi", ctx).rows[1]
    assert api.act(FakeKind, "set_tag", [choice.id], ctx) == "Tagged 2 notes: scifi", "every untagged row gets it"


def test_command_return_offers_the_picker_on_every_row(served):
    ctx, _ = served
    (row,) = api.filter(FakeKind, "ubik", ctx).rows
    assert ("cmd", "pick") in [(mod.key, mod.verb) for mod in row.mods], "⌘↩ should open the tag picker"


def test_dry_run_prints_evidence_and_schema_and_sends_nothing(served, replies, capsys, monkeypatch):
    ctx, _ = served
    urlopen = replies()
    for name, value in {**ctx.config, "alfred_workflow_data": ctx.data, "alfred_workflow_cache": ctx.cache}.items():
        monkeypatch.setenv(name, value)
    cli.main("hoard.testing.fake", ["ask", "name", "--dry-run"])
    out = capsys.readouterr().out
    assert '"required": ["title", "author", "year", "confidence"]' in out, "the schema should be printed"
    assert "Dune by Frank Herbert, 1965" in out and "— Ubik" in out, "each entity's evidence should be printed"
    urlopen.assert_not_called()


def test_return_on_ask_starts_the_worker(served, mocker, capsys, monkeypatch):
    ctx, _ = served
    for name, value in {**ctx.config, "alfred_workflow_data": ctx.data, "alfred_workflow_cache": ctx.cache}.items():
        monkeypatch.setenv(name, value)
    spawn = mocker.patch("hoard._worker.spawn", return_value=True)
    cli.main("hoard.testing.fake", ["act", "ask", "ask:name"])
    assert capsys.readouterr().out == "Asking the model\n", "↩ on Ask should hand the job to the worker"
    assert spawn.call_args.args[:2] == ("hoard.testing.fake", "ask"), "the worker should run the ask job"


def in_environment(monkeypatch, ctx, **extra):
    for name, value in {**ctx.config, "alfred_workflow_data": ctx.data, "alfred_workflow_cache": ctx.cache, **extra}.items():
        monkeypatch.setenv(name, value)


@pytest.mark.parametrize(
    "argv, setting, asked",
    [
        (["worker", "ask"], "", True),
        (["worker", "update"], "1", True),
        (["worker", "update"], "", False),
    ],
)
def test_the_worker_asks_on_demand_or_after_an_update_when_set(served, replies, monkeypatch, argv, setting, asked):
    ctx, _ = served
    in_environment(monkeypatch, ctx, hoard_ask_on_update=setting, fake_tags="")
    urlopen = replies(named("Dune", "Frank Herbert", "1965", 0.95), named("Ubik", "Philip K. Dick", "1969", 0.9))
    cli.main("hoard.testing.fake", argv)
    assert (urlopen.call_count == 2) is asked, f"{argv} with ask-on-update {setting!r} should ask: {asked}"


@pytest.mark.parametrize("answer", [{"title": "Dune", "confidence": 0.9}, None], ids=["answered", "unanswered"])
def test_asking_counts_every_entity_asked_out_of_all_stale_questions(served, mocker, answer):
    from hoard import _progress

    ctx, _ = served
    watcher = _db.connect(_db.path_for("fake", ctx.data))
    seen = []

    def answering(*args, **kwargs):
        seen.append(_progress.current(watcher))
        return answer

    mocker.patch("hoard._oracle.ask", side_effect=answering)
    api.ask(FakeKind, ctx, ["name", "tag"])
    assert seen == [("ask", str(n), "4") for n in range(4)], "each call should see how many were asked before it, out of all"
    assert _progress.current(watcher) == ("ask", "4", "4"), "the end should count every entity asked, answered or not"
    watcher.close()
