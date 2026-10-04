from __future__ import annotations

import pytest

from hoard.testing import builders


@pytest.fixture
def temp_tree(tmp_path):
    def build(spec, root="tree"):
        return builders.temp_tree(tmp_path / root, spec)

    return build


@pytest.fixture
def context_with(tmp_path):
    def build(**config):
        return builders.make_context(tmp_path / "workflow", **config)

    return build
