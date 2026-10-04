from __future__ import annotations

import pytest

from hoard import _answers


@pytest.fixture
def indexed(tmp_db):
    tmp_db.executemany(
        "INSERT INTO entities(id, title, fields_json, evidence, evidence_hash) VALUES (?, ?, '[]', ?, ?)",
        [("id1", "Dune", "Dune", "h1"), ("id2", "Ubik", "Ubik", "h2"), ("id3", "Bare", None, None)],
    )
    return tmp_db


def test_a_stored_answer_is_fresh_for_the_same_evidence(indexed):
    _answers.store(indexed, "id1", "name", "h1", "qwen", {"title": "Dune"})
    assert _answers.fresh(indexed, "id1", "name", "h1") == {"title": "Dune"}, "the same evidence should reuse the answer"
    assert _answers.fresh(indexed, "id1", "name", "h9") is None, "changed evidence should make the answer stale"


def test_stale_lists_entities_without_a_fresh_answer(indexed):
    _answers.store(indexed, "id1", "name", "h1", "qwen", {"title": "Dune"})
    _answers.store(indexed, "id2", "name", "old", "qwen", {"title": "Ubik"})
    assert _answers.stale(indexed, "name") == [("id2", "Ubik")], (
        "only entities with evidence and a missing or outdated answer should be asked"
    )


def test_forgetting_an_answer_makes_it_stale_again(indexed):
    _answers.store(indexed, "id1", "tag", "h1", "qwen", {"tag": "scifi"})
    _answers.forget(indexed, "id1", "tag")
    assert ("id1", "Dune") in _answers.stale(indexed, "tag"), "a forgotten answer should be asked again"


def test_exchanges_keep_only_the_most_recent(tmp_db):
    for n in range(7):
        _answers.record_exchange(tmp_db, "chat", {"n": n}, {"ok": n}, keep=5)
    kept = [row[0] for row in tmp_db.execute("SELECT request FROM exchanges ORDER BY at, rowid")]
    assert kept == [f'{{"n": {n}}}' for n in range(2, 7)], "the log should be trimmed to the newest rows"
