from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from hoard import _index, api
from hoard.contract import STEP_VERBS, Context, Entity, Kind, Storage
from hoard.items import Item
from hoard.render import text

KEYSTROKE_BANNED = ("zipfile", "urllib", "xml", "http", "pytest", "hoard.testing", "hoard.build")


@dataclass(frozen=True)
class fixed_roots:
    roots: tuple

    def __call__(self, ctx: Context) -> list:
        return list(self.roots)


def with_sample_roots(kind: Kind, roots: dict) -> Kind:
    storages = tuple(
        s._replace(roots=fixed_roots((str(roots[s.name]),)), mounted=os.path.isdir)
        for s in kind.storages
    )
    return kind._replace(storages=storages)


def files_under(root: Path) -> list:
    return [path for path, _ in _index.walk(str(root))]


def read_samples(storage: Storage, root: Path) -> list:
    return [entity for entity in map(storage.reader, files_under(root)) if entity is not None]


@dataclass(frozen=True)
class Samples:
    kind: Kind
    ctx: Context
    entities: tuple
    roots: tuple = ()


def snapshot(roots) -> dict:
    return {
        (str(root), str(path.relative_to(root))): path.read_bytes()
        for root in roots
        for path in sorted(Path(root).rglob("*"))
        if path.is_file()
    }


def listed_ids(kind: Kind, ctx: Context) -> list:
    return [row.id for row in api.filter(kind, "", ctx).rows if isinstance(row, Item)]


def module_defining(kind: Kind) -> str:
    found = next((name for name, module in list(sys.modules.items()) if getattr(module, "KIND", None) is kind), None)
    assert found, "the kind under test should be the KIND of an importable module"
    return found


def source_files(module_name: str) -> list:
    module = sys.modules[module_name]
    if hasattr(module, "__path__"):
        return sorted(str(p) for folder in module.__path__ for p in Path(folder).rglob("*.py"))
    return [module.__file__]


def imported_names(path: str) -> set:
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def private_hoard_imports(path: str) -> list:
    return sorted(
        name for name in imported_names(path) if name.startswith("hoard.") and any(p.startswith("_") for p in name.split(".")[1:])
    )


def modules_loaded_by_import(module_name: str) -> list:
    probe = f"import json, sys, {module_name}; print(json.dumps(sorted(sys.modules)))"
    environ = dict(os.environ, PYTHONPATH=os.pathsep.join(path for path in sys.path if path))
    finished = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, env=environ, check=True)
    return json.loads(finished.stdout)


def banned_among(loaded: list, banned: tuple) -> list:
    return sorted(name for name in loaded if any(name == b or name.startswith(b + ".") for b in banned))


class Conformance:
    kind: Kind = None
    keystroke_banned = KEYSTROKE_BANNED

    def make_samples(self, storage: str, root: Path) -> None:
        pass

    @pytest.fixture
    def samples(self, tmp_path) -> Samples:
        roots = {}
        for storage in self.kind.storages:
            roots[storage.name] = tmp_path / "samples" / storage.name
            roots[storage.name].mkdir(parents=True)
            self.make_samples(storage.name, roots[storage.name])
        kind = with_sample_roots(self.kind, roots)
        entities = tuple(e for s in kind.storages for e in read_samples(s, roots[s.name]))
        ctx = Context(data=str(tmp_path / "data"), cache=str(tmp_path / "cache"))
        os.makedirs(ctx.data)
        os.makedirs(ctx.cache)
        return Samples(kind, ctx, entities, tuple(roots.values()))

    def test_kind_is_a_kind(self):
        assert isinstance(self.kind, Kind), "KIND should be a hoard.contract.Kind"

    def test_storages_are_ordered_and_named(self):
        names = [storage.name for storage in self.kind.storages]
        assert isinstance(self.kind.storages, tuple), "storages should be a tuple, in display order"
        assert len(names) == len(set(names)), "storage names should be unique"

    def test_fields_are_labels(self):
        assert all(isinstance(f, str) and f for f in self.kind.fields), "every field should be a non-empty label"

    def test_every_entity_has_one_string_per_field(self, samples):
        for entity in samples.entities:
            assert isinstance(entity, Entity), "a reader should return Entity records or None"
            assert len(entity.fields) == len(self.kind.fields), f"{entity.title} should have a value per field"
            assert all(isinstance(value, str) for value in entity.fields), f"{entity.title} fields should be strings"

    def test_every_entity_has_a_text_id_and_title(self, samples):
        for entity in samples.entities:
            assert isinstance(entity.id, str) and entity.id, "an entity id should be non-empty text"
            assert isinstance(entity.title, str) and entity.title, "an entity should have a title"

    def test_evidence_is_text(self, samples):
        for entity in samples.entities:
            assert isinstance(self.kind.evidence(entity), str), f"evidence for {entity.title} should be a string"

    def test_samples_list_through_the_text_renderer(self, samples):
        api.update(samples.kind, samples.ctx)
        lines = text.render(api.filter(samples.kind, "", samples.ctx))
        distinct = len({entity.id for entity in samples.entities})
        expected = min(distinct, 40) if distinct else 1
        assert len(lines) == expected, "an empty query should list every sample, or say the index is empty"
        assert all(isinstance(line, str) for line in lines), "every row should render as a line"

    def test_every_command_lists_through_the_text_renderer(self, samples):
        api.update(samples.kind, samples.ctx)
        for word in self.kind.commands:
            lines = text.render(api.filter(samples.kind, word, samples.ctx))
            assert lines and all(isinstance(line, str) for line in lines), f"{word} should list through the renderer"

    def test_undoable_verbs_undo_to_the_byte(self, samples):
        api.update(samples.kind, samples.ctx)
        ids = listed_ids(samples.kind, samples.ctx)
        for name, verb in self.kind.verbs.items():
            if not verb.undoable:
                continue
            before = snapshot(samples.roots)
            api.act(samples.kind, name, ids, samples.ctx)
            api.act(samples.kind, "undo", [], samples.ctx)
            assert snapshot(samples.roots) == before, f"{name} then undo should leave every sample byte-identical"

    def test_the_plan_uses_kernel_steps_and_undoes_to_the_byte(self, samples):
        if self.kind.lint is None:
            return
        api.update(samples.kind, samples.ctx)
        steps = api.plan(samples.kind, "", samples.ctx)
        assert all(step.verb in STEP_VERBS for step in steps), f"plan steps should use {sorted(STEP_VERBS)}"
        before = snapshot(samples.roots)
        api.act(samples.kind, "apply", ["plan:"], samples.ctx)
        api.act(samples.kind, "undo", [], samples.ctx)
        assert snapshot(samples.roots) == before, "applying the plan then undoing should leave every byte in place"

    def test_verbs_declare_undo(self):
        for name, verb in self.kind.verbs.items():
            assert verb.undo is None or callable(verb.undo), f"verb {name} should declare undo or None"

    def test_kind_imports_no_private_hoard_module(self):
        for path in source_files(module_defining(self.kind)):
            assert private_hoard_imports(path) == [], f"{path} should import only hoard's public surface"

    def test_importing_the_kind_stays_off_the_slow_path(self):
        loaded = modules_loaded_by_import(module_defining(self.kind))
        assert banned_among(loaded, self.keystroke_banned) == [], (
            "importing the kind should not load readers, HTTP or test code; wrap them in lazy()"
        )
