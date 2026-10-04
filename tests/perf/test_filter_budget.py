from __future__ import annotations

import time

import pytest

from hoard import api
from hoard.testing import FakeKind
from hoard.testing.fake import write_note

ENTITIES = 10_000
WARM_BUDGET = 0.050
WORDS = ("amber", "basalt", "cedar", "delta", "ember", "fjord", "garnet", "harbor", "indigo", "juniper")

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def large_library(tmp_path_factory):
    from hoard.testing import make_context

    base = tmp_path_factory.mktemp("perf")
    shelf = base / "shelf"
    for n in range(ENTITIES):
        title = f"{WORDS[n % 10].title()} {WORDS[(n // 10) % 10]} {n}"
        write_note(shelf, f"{n // 1000}/{n}", title, f"Author {n % 97}", str(1900 + n % 120), mtime=1_000_000 + n)
    ctx = make_context(base / "workflow", fake_shelf=str(shelf))
    api.update(FakeKind, ctx)
    return ctx


def warm_seconds(ctx, typed: str) -> float:
    api.filter(FakeKind, typed, ctx)
    started = time.perf_counter()
    api.filter(FakeKind, typed, ctx)
    return time.perf_counter() - started


@pytest.mark.parametrize("typed", ["", "a", "amber", "amber cedar", "author 5", "zzz"])
def test_filter_answers_within_the_warm_budget(large_library, typed):
    elapsed = warm_seconds(large_library, typed)
    assert elapsed < WARM_BUDGET, f"{typed!r} over {ENTITIES} entities should answer under 50 ms warm, took {elapsed * 1000:.1f} ms"
