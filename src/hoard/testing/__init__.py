from __future__ import annotations

import os

import pytest

from hoard.contract import Context
from hoard.testing import builders
from hoard.testing.fake import KIND as FakeKind

__all__ = ["FakeKind", "make_context"]


def make_context(base, **config: str) -> Context:
    data = os.path.join(str(base), "data")
    cache = os.path.join(str(base), "cache")
    os.makedirs(data, exist_ok=True)
    os.makedirs(cache, exist_ok=True)
    return Context(data=data, cache=cache, config=dict(config))


@pytest.fixture
def temp_tree(tmp_path):
    def build(spec, root="tree"):
        return builders.temp_tree(tmp_path / root, spec)

    return build


@pytest.fixture
def context_with(tmp_path):
    def build(**config):
        return make_context(tmp_path / "workflow", **config)

    return build
