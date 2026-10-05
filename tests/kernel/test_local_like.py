from __future__ import annotations

import pytest

from hoard import api
from hoard.contract import ContractError, LocalVectors
from hoard.render import text
from hoard.testing import FakeKind
from hoard.testing.fake import write_note

AUTHORS = ("Herbert", "Dick", "Le Guin")


def by_author(found, ctx) -> list:
    author = found.entity.fields[0]
    return [1.0 if name in author else 0.0 for name in AUTHORS] + [0.05]


LOCAL = FakeKind._replace(like=LocalVectors("authors", by_author))


@pytest.fixture
def library(ctx, shelf):
    write_note(shelf, "dune", "Dune", "Frank Herbert", mtime=4000)
    write_note(shelf, "messiah", "Dune Messiah", "Frank Herbert", mtime=3000)
    write_note(shelf, "ubik", "Ubik", "Philip K. Dick", mtime=2000)
    write_note(shelf, "lathe", "The Lathe of Heaven", "Ursula K. Le Guin", mtime=1000)
    return ctx


def lines(kind, ctx, typed):
    return text.render(api.filter(kind, typed, ctx))


def test_update_makes_local_vectors_and_like_needs_no_server(library):
    api.update(LOCAL, library)
    result = lines(LOCAL, library, "like dune")
    assert result[0] == "» Like Dune | 3 neighbours", "like should work with no model server at all"
    assert result[1].startswith("Dune Messiah | 100% · "), "the same author should be nearest"


def test_local_vectors_are_made_once(library, mocker):
    vector = mocker.Mock(side_effect=by_author)
    kind = FakeKind._replace(like=LocalVectors("authors", vector))
    api.update(kind, library)
    vector.reset_mock()
    api.update(kind, library)
    vector.assert_not_called()


def test_the_vector_is_given_the_context(library, mocker):
    vector = mocker.Mock(side_effect=by_author)
    api.update(FakeKind._replace(like=LocalVectors("authors", vector)), library)
    assert {call.args[1].cache for call in vector.call_args_list} == {library.cache}, (
        "a kind should get the context, e.g. to find its cache folder"
    )


def test_a_failing_vector_skips_that_entity(library):
    def fragile(found, ctx):
        if found.entity.title == "Ubik":
            raise ValueError("no metadata")
        return by_author(found, ctx)

    kind = FakeKind._replace(like=LocalVectors("authors", fragile))
    api.update(kind, library)
    assert lines(kind, library, "like ubik") == ["» Ubik has no vector yet"], "a failed vector should leave a gap"
    assert lines(kind, library, "like dune")[0] == "» Like Dune | 2 neighbours", "the others should still be compared"


def test_local_like_offers_control_return_without_a_server(library):
    api.update(LOCAL, library)
    (row,) = api.filter(LOCAL, "ubik", library).rows
    assert ("ctrl", "like") in [(mod.key, mod.verb) for mod in row.mods], "⌃↩ should be offered for local like"


def test_local_like_never_offers_to_embed(library):
    api.update(LOCAL, library)
    assert not any(line.startswith("» Embed") for line in lines(LOCAL, library, "like dune")), (
        "local vectors are made by update, so there is nothing to embed"
    )


@pytest.mark.parametrize("like", ["text", LocalVectors("", by_author), LocalVectors("x", "not callable")])
def test_a_malformed_like_strategy_fails_when_built(like):
    with pytest.raises(ContractError):
        FakeKind.__class__(*FakeKind._replace(like=like))


def test_local_vectors_count_as_embedding_during_an_update(library, mocker):
    from hoard import _db, _progress

    mocker.patch("hoard._progress.EVERY", 1)
    watcher = _db.connect(_db.path_for(FakeKind.name, library.data))
    seen = []

    def watching(found, ctx):
        seen.append(_progress.current(watcher))
        return by_author(found, ctx)

    api.update(FakeKind._replace(like=LocalVectors("authors", watching)), library)
    assert seen == [("embed", str(n), "4") for n in range(4)], "local vectors should be counted as embedding, not as checking"
    watcher.close()
