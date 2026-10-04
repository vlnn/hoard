from __future__ import annotations

import random
import time
from array import array

import pytest

from hoard import _db, _neighbours, _vectors

VECTORS = 10_000
DIMENSIONS = 1024
INSERT_BUDGET = 2.0

pytestmark = pytest.mark.slow


def random_unit(rng: random.Random) -> array:
    return _vectors.normalized(array("f", (rng.gauss(0, 1) for _ in range(DIMENSIONS))))


@pytest.fixture(scope="module")
def crowded(tmp_path_factory):
    rng = random.Random(7)
    con = _db.connect(str(tmp_path_factory.mktemp("vectors") / "kind.sqlite"))
    con.executemany(
        "INSERT INTO vectors(model, id, vec) VALUES ('m', ?, ?)",
        ((f"id{n}", _vectors.packed(random_unit(rng))) for n in range(VECTORS)),
    )
    con.commit()
    yield con, rng
    con.close()


def test_one_insert_among_ten_thousand_stays_near_a_second(crowded):
    con, rng = crowded
    newcomer = random_unit(rng)
    started = time.perf_counter()
    _neighbours.insert(con, "m", "newcomer", newcomer)
    elapsed = time.perf_counter() - started
    assert elapsed < INSERT_BUDGET, f"inserting among {VECTORS} × {DIMENSIONS} should take about a second, took {elapsed:.2f} s"
    assert con.execute("SELECT count(*) FROM neighbours WHERE id = 'newcomer'").fetchone() == (20,), "it keeps twenty"
