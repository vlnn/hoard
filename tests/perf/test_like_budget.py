from __future__ import annotations

import os
import random
import time
from array import array

import pytest

from hoard import _db, _nearest, _signatures, _vectors

VECTORS = 10_000
DIMENSIONS = 1024
LIKE_BUDGET = 0.05

pytestmark = pytest.mark.slow


def random_unit(rng: random.Random) -> array:
    return _vectors.normalized(array("f", (rng.gauss(0, 1) for _ in range(DIMENSIONS))))


@pytest.fixture(scope="module")
def crowded(tmp_path_factory):
    rng = random.Random(7)
    con = _db.connect(str(tmp_path_factory.mktemp("vectors") / "kind.sqlite"))
    con.executemany(
        "INSERT INTO vectors(model, id, vec, sig) VALUES ('m', ?, ?, ?)",
        ((f"id{n}", _vectors.packed(random_unit(rng)), os.urandom(_signatures.BITS // 8)) for n in range(VECTORS)),
    )
    _vectors.store(con, "m", "seed", random_unit(rng))
    con.commit()
    yield con
    con.close()


def test_like_among_ten_thousand_stays_within_a_keystroke(crowded):
    _nearest.nearest(crowded, "m", "seed")
    started = time.perf_counter()
    ranked = _nearest.nearest(crowded, "m", "seed")
    elapsed = time.perf_counter() - started
    assert elapsed < LIKE_BUDGET, f"ranking among {VECTORS} × {DIMENSIONS} should fit a warm keystroke, took {elapsed:.3f} s"
    assert len(ranked) == _nearest.CANDIDATES, "every shortlisted vector should be scored"


def test_signing_a_vector_stays_cheap():
    vector = random_unit(random.Random(5))
    _signatures.of(vector)
    started = time.perf_counter()
    for _ in range(100):
        _signatures.of(vector)
    each = (time.perf_counter() - started) / 100
    assert each < 0.005, f"signing a {DIMENSIONS}-dimension vector should take a few milliseconds, took {each * 1000:.1f} ms"
