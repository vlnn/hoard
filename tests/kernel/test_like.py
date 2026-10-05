from __future__ import annotations

import json
from array import array

import pytest

from hoard import _db, _vectors, api, cli
from hoard.contract import TextEmbedding
from hoard.render import text
from hoard.testing import FakeKind
from hoard.testing.fake import read_note, write_note

WORDS = ("desert", "spice", "android", "robot")
EMBEDDINGS = {"hoard_embeddings_url": "http://e:8081", "fake_tags": ""}


def vector_of(evidence: str) -> list:
    lowered = evidence.lower()
    return [float(lowered.count(word)) + 0.01 for word in WORDS]


@pytest.fixture
def embedder(mocker):
    def answer(request, timeout=None):
        inputs = json.loads(request.data.decode("utf-8"))["input"]
        reply = mocker.MagicMock()
        data = [{"index": n, "embedding": vector_of(text_)} for n, text_ in enumerate(inputs)]
        reply.__enter__.return_value.read.return_value = json.dumps({"data": data}).encode("utf-8")
        return reply

    return mocker.patch("urllib.request.urlopen", side_effect=answer)


@pytest.fixture
def library(context_with, shelf, satchel):
    shelf.mkdir()
    satchel.mkdir()
    ctx = context_with(fake_shelf=str(shelf), fake_satchel=str(satchel), **EMBEDDINGS)
    notes = {
        "dune": ("Dune", "desert spice desert", 4000),
        "messiah": ("Dune Messiah", "desert spice", 3000),
        "ubik": ("Ubik", "android robot", 2000),
        "sheep": ("Electric Sheep", "android android robot", 1000),
    }
    ids = {
        key: read_note(write_note(shelf, key, title, body=body, mtime=mtime)).id for key, (title, body, mtime) in notes.items()
    }
    api.update(FakeKind, ctx)
    return ctx, ids


def lines(ctx, typed):
    return text.render(api.filter(FakeKind, typed, ctx))


def test_vectors_are_stored_unit_length():
    stored = _vectors.normalized(array("f", [3.0, 4.0]))
    assert [round(x, 6) for x in stored] == [0.6, 0.8], "vectors should be scaled to unit length"


def test_a_zero_vector_stays_zero():
    assert list(_vectors.normalized(array("f", [0.0, 0.0]))) == [0.0, 0.0], "nothing should be divided by zero"


def test_vectors_round_trip_through_a_blob():
    vector = array("f", [0.25, -1.5, 3.0])
    assert _vectors.unpacked(_vectors.packed(vector)) == vector, "a stored blob should read back exactly"


def test_embedding_stores_every_vector_with_its_signature(library, embedder):
    ctx, _ = library
    assert api.embed(FakeKind, ctx) == 4, "every entity with evidence should get a vector"
    con = _db.connect(_db.path_for("fake", ctx.data))
    (count,) = con.execute("SELECT count(*) FROM vectors WHERE sig IS NOT NULL").fetchone()
    con.close()
    assert count == 4, "each vector should be stored with the signature like searches by"


def test_like_lists_the_nearest_first_with_a_percentage(library, embedder):
    ctx, _ = library
    api.embed(FakeKind, ctx)
    result = lines(ctx, "like dune")
    assert result[0] == "» Like Dune | 3 neighbours", "the head should name the seed"
    assert result[1].startswith("Dune Messiah | ") and "% · shelf · " in result[1], "the closest should lead, with a score"
    assert [line.split(" | ")[0] for line in result[2:]] == ["Electric Sheep", "Ubik"] or [
        line.split(" | ")[0] for line in result[2:]
    ] == ["Ubik", "Electric Sheep"], "the rest should follow"
    assert int(result[1].split(" | ")[1].split("%")[0]) > int(result[2].split(" | ")[1].split("%")[0]), (
        "scores should fall down the list"
    )


def test_like_by_id_seeds_from_that_entity(library, embedder):
    ctx, ids = library
    api.embed(FakeKind, ctx)
    assert lines(ctx, f"like #{ids['ubik']}")[1].startswith("Electric Sheep | "), "#id should seed from that entity"


def test_like_alone_seeds_from_the_last_opened_or_the_newest(library, embedder):
    ctx, ids = library
    api.embed(FakeKind, ctx)
    assert lines(ctx, "like")[0] == "» Like Dune | 3 neighbours", "without words the newest should seed"
    kind = FakeKind._replace(last_opened=lambda ctx: ids["sheep"])
    assert text.render(api.filter(kind, "like", ctx))[0] == "» Like Electric Sheep | 3 neighbours", (
        "the kind's last opened entity should seed when it has one"
    )


def test_copies_with_the_same_title_are_not_their_own_neighbours(library, embedder, shelf):
    ctx, _ = library
    write_note(shelf, "dune second edition", "Dune", body="desert spice desert ", mtime=500)
    api.update(FakeKind, ctx)
    api.embed(FakeKind, ctx)
    assert all(not line.startswith("Dune |") for line in lines(ctx, "like dune")[1:]), "another Dune is not a neighbour"


def test_new_entities_are_offered_for_embedding(library, embedder, shelf):
    ctx, _ = library
    api.embed(FakeKind, ctx)
    write_note(shelf, "arrakis", "Arrakis", body="desert")
    api.update(FakeKind, ctx)
    assert "» Embed 1 new | the model runs in the background" in lines(ctx, "like dune"), "new entities should be offered"


def test_like_before_any_vector_says_so(library):
    ctx, _ = library
    assert lines(ctx, "like dune") == [
        "» Embed 4 new | the model runs in the background",
        "» Dune has no vector yet",
    ], "without vectors like should offer to embed and say why it shows nothing"


def test_like_without_an_embeddings_server_is_a_search_word(library):
    ctx, _ = library
    plain = ctx._replace(config={"fake_shelf": ctx.config["fake_shelf"], "fake_satchel": ctx.config["fake_satchel"]})
    assert not any(line.startswith("» ") for line in lines(plain, "like dune")), "no server means no like command"


def test_control_return_reopens_alfred_at_like(library, mocker):
    ctx, ids = library
    run = mocker.patch("subprocess.run")
    (row,) = api.filter(FakeKind, "ubik", ctx).rows
    assert ("ctrl", "like") in [(mod.key, mod.verb) for mod in row.mods], "⌃↩ should mean like"
    api.act(FakeKind, "like", [row.id], ctx)
    assert f'search "fk like #{ids["ubik"]}"' in run.call_args.args[0][-1], "Alfred should reopen at like #id"


def test_the_worker_embeds_after_asking(library, embedder, monkeypatch):
    ctx, _ = library
    for name, value in {**ctx.config, "alfred_workflow_data": ctx.data, "alfred_workflow_cache": ctx.cache}.items():
        monkeypatch.setenv(name, value)
    cli.main("hoard.testing.fake", ["worker", "ask"])
    assert lines(ctx, "like dune")[0] == "» Like Dune | 3 neighbours", "the ask job should embed too"


def test_text_embedding_is_the_default_strategy():
    assert FakeKind.like == TextEmbedding(), "a kind should get like for free"


def test_embedding_counts_every_batch_out_of_all_missing(library, embedder, mocker):
    from hoard import _progress

    ctx, _ = library
    mocker.patch("hoard._embed.BATCH", 3)
    watcher = _db.connect(_db.path_for("fake", ctx.data))
    seen = []
    answer = embedder.side_effect

    def watching(request, timeout=None):
        seen.append(_progress.current(watcher))
        return answer(request, timeout)

    embedder.side_effect = watching
    api.embed(FakeKind, ctx)
    assert seen == [("embed", "0", "4"), ("embed", "3", "4")], "each batch should see what was embedded before it"
    assert _progress.current(watcher) == ("embed", "4", "4"), "the end should count every vector"
    watcher.close()
