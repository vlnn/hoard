from __future__ import annotations

import importlib

pytest_plugins = ["hoard.testing.plugin"]

EXPORTS = {
    "Conformance": ("hoard.testing.conformance", "Conformance"),
    "FakeKind": ("hoard.testing.fake", "KIND"),
    "make_context": ("hoard.testing.builders", "make_context"),
    "make_epub": ("hoard.testing.builders", "make_epub"),
    "make_fb2": ("hoard.testing.builders", "make_fb2"),
}

__all__ = sorted(EXPORTS)


def __getattr__(name: str):
    if name not in EXPORTS:
        raise AttributeError(f"module 'hoard.testing' has no attribute {name!r}")
    module, attribute = EXPORTS[name]
    return getattr(importlib.import_module(module), attribute)
