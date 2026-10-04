from __future__ import annotations

import random
from array import array

import pytest

from hoard import _db, _nearest, _signatures, _vectors


def unit(values) -> array:
    return _vectors.normalized(array("f", values))


def random_unit(rng: random.Random, dimensions: int) -> array:
    return unit(rng.gauss(0, 1) for _ in range(dimensions))


def nudged(rng: random.Random, vector: array, by: float) -> array:
    return unit(x + rng.gauss(0, by) for x in vector)


@pytest.mark.parametrize("dimensions", [1, 2, 4, 341, 1024])
def test_a_signature_has_a_fixed_size(dimensions):
    signature = _signatures.of(unit([1.0] * dimensions))
    assert len(signature) == _signatures.BITS // 8, "every signature should be the same number of bytes"


def test_a_signature_is_the_same_every_time():
    vector = random_unit(random.Random(1), 64)
    _signatures.planes.cache_clear()
    first = _signatures.of(vector)
    _signatures.planes.cache_clear()
    assert _signatures.of(vector) == first, "planes should come from a fixed seed, not from the process"


def test_close_vectors_have_close_signatures():
    rng = random.Random(3)
    vector = random_unit(rng, 256)
    near = _signatures.distance(_signatures.of(vector), _signatures.of(nudged(rng, vector, 0.01)))
    far = _signatures.distance(_signatures.of(vector), _signatures.of(random_unit(rng, 256)))
    assert near < far, "a slightly moved vector should differ in fewer bits than an unrelated one"


@pytest.fixture
def stored(tmp_db):
    def store(vectors: dict, model: str = "m") -> None:
        for entity_id, values in vectors.items():
            _vectors.store(tmp_db, model, entity_id, unit(values))

    return store


def test_the_nearest_come_first_with_exact_scores(tmp_db, stored):
    stored({"a": [1.0, 0.0], "b": [0.0, 1.0], "c": [0.6, 0.8]})
    ranked = _nearest.nearest(tmp_db, "m", "a")
    assert [entity_id for _, entity_id in ranked] == ["c", "b"], "the closer vector should rank first"
    assert [round(score, 4) for score, _ in ranked] == [0.6, 0.0], "scores should be exact cosines"


def test_the_seed_and_other_models_are_left_out(tmp_db, stored):
    stored({"a": [1.0, 0.0], "b": [0.9, 0.1]})
    stored({"x": [1.0, 0.0]}, model="other")
    assert [entity_id for _, entity_id in _nearest.nearest(tmp_db, "m", "a")] == ["b"], (
        "only other vectors of the same model should be compared"
    )


def test_a_seed_without_a_vector_has_no_neighbours(tmp_db, stored):
    stored({"a": [1.0, 0.0]})
    assert _nearest.nearest(tmp_db, "m", "missing") == [], "nothing should be ranked without a seed vector"


def test_planted_clusters_are_found_among_thousands(tmp_db):
    rng = random.Random(11)
    clusters, members, dimensions = 60, 20, 256
    for cluster in range(clusters):
        centre = random_unit(rng, dimensions)
        for member in range(members):
            _vectors.store(tmp_db, "m", f"{cluster}-{member}", nudged(rng, centre, 0.02))
    nearest = [entity_id for _, entity_id in _nearest.nearest(tmp_db, "m", "42-0")[: members - 1]]
    assert sorted(nearest) == sorted(f"42-{member}" for member in range(1, members)), (
        "the signature shortlist should keep every member of the seed's own cluster"
    )


def test_the_schema_keeps_signatures_and_no_neighbours(tmp_db):
    tables = {name for (name,) in tmp_db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    columns = {row[1] for row in tmp_db.execute("PRAGMA table_info(vectors)")}
    assert "neighbours" not in tables, "neighbours are ranked when asked, so the table should be gone"
    assert "sig" in columns, "vectors should carry their signature"


def test_the_shortlist_reads_signatures_from_an_index(tmp_db):
    plan = " ".join(row[-1] for row in tmp_db.execute("EXPLAIN QUERY PLAN " + _nearest.SIGNED, ("m", "a")))
    assert "COVERING INDEX" in plan, "scanning signatures should not read the vector blobs"


def test_a_vector_stored_before_signatures_counts_as_missing(tmp_db):
    tmp_db.execute("INSERT INTO entities(id, title, fields_json, evidence) VALUES ('a', 'A', '[]', 'some evidence')")
    tmp_db.execute("INSERT INTO vectors(model, id, vec) VALUES ('m', 'a', ?)", (_vectors.packed(unit([1.0])),))
    assert [row[0] for row in _vectors.missing(tmp_db, "m")] == ["a"], "an unsigned vector should be made again"
    assert [row[0] for row in _vectors.without_vector(tmp_db, "m")] == ["a"], "local vectors too"
