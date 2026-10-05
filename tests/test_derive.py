from __future__ import annotations

import pytest

from hoard import _index, api
from hoard.render import text
from hoard.contract import LocalVectors
from hoard.testing import FakeKind
from hoard.testing.fake import write_note


def shouted(found, ctx) -> str:
    with open(found.nearest.locator, encoding="utf-8") as handle:
        return handle.read().partition("\n\n")[2].upper()


def deriving(producer):
    return FakeKind._replace(derive={"shout": producer})


def derived_rows(con):
    return sorted(con.execute("SELECT key, value, source FROM derived"))


@pytest.fixture
def notes(shelf):
    write_note(shelf, "dune", "Dune", body="spice must flow")
    write_note(shelf, "ubik", "Ubik", body="")


def test_update_fills_each_missing_derived_value(tmp_db, ctx, notes):
    _index.update(tmp_db, deriving(shouted), ctx)
    assert derived_rows(tmp_db) == [("shout", "", "shout"), ("shout", "SPICE MUST FLOW", "shout")], (
        "every entity should get the derived value, empty ones included so they are not asked again"
    )


def test_derived_values_are_searchable(ctx, notes):
    kind = deriving(shouted)
    api.update(kind, ctx)
    assert text.render(api.filter(kind, "flow", ctx))[0].startswith("Dune | "), "search should reach derived text"


def test_a_second_update_derives_nothing_again(tmp_db, ctx, notes, mocker):
    producer = mocker.Mock(side_effect=shouted)
    _index.update(tmp_db, deriving(producer), ctx)
    producer.reset_mock()
    _index.update(tmp_db, deriving(producer), ctx)
    producer.assert_not_called()


def test_a_full_rebuild_keeps_derived_values_without_asking_again(tmp_db, ctx, notes, mocker):
    producer = mocker.Mock(side_effect=shouted)
    _index.update(tmp_db, deriving(producer), ctx)
    producer.reset_mock()
    _index.update(tmp_db, deriving(producer), ctx, full=True)
    producer.assert_not_called()
    assert ("shout", "SPICE MUST FLOW", "shout") in derived_rows(tmp_db), "a full rebuild should keep derived values"


def test_a_failing_producer_is_skipped_and_asked_again_next_time(tmp_db, ctx, notes, mocker):
    producer = mocker.Mock(side_effect=OSError("no OCR today"))
    _index.update(tmp_db, deriving(producer), ctx)
    assert derived_rows(tmp_db) == [], "a failure should store nothing"
    producer.reset_mock()
    _index.update(tmp_db, deriving(producer), ctx)
    assert producer.call_count == 2, "both entities should be asked again on the next update"


def test_a_new_producer_runs_for_entities_already_indexed(tmp_db, ctx, notes):
    _index.update(tmp_db, FakeKind, ctx)
    _index.update(tmp_db, deriving(shouted), ctx)
    assert len(derived_rows(tmp_db)) == 2, "adding a producer should derive for unchanged files too"


def test_a_producer_is_given_the_context(tmp_db, ctx, notes, mocker):
    producer = mocker.Mock(side_effect=shouted)
    _index.update(tmp_db, deriving(producer), ctx)
    assert {call.args[1].cache for call in producer.call_args_list} == {ctx.cache}, (
        "a producer should get the context, e.g. to find its cache folder"
    )


def test_local_vectors_are_made_before_derived_values(tmp_db, ctx, notes):
    calls = []

    def vector(found, ctx):
        calls.append(("vector", found.entity.title))
        return [1.0]

    def producer(found, ctx):
        calls.append(("derive", found.entity.title))
        return ""

    kind = deriving(producer)._replace(like=LocalVectors("order", vector))
    _index.update(tmp_db, kind, ctx)
    assert [step for step, _ in calls] == ["vector", "vector", "derive", "derive"], (
        "a kind that analyses once should see the vector pass first and reuse it for derived values"
    )
