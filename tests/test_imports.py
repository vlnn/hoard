from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import sysconfig
from pathlib import Path

import pytest

from hoard.testing.conformance import imported_names

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "hoard"
PUBLIC = {"__init__", "__main__", "contract", "api", "items", "cli", "new"}
SUBPACKAGES = {"render", "testing", "build", "template"}
DEV_ONLY = {"testing": {"pytest"}}
KIND_NAMES = re.compile(r"\b(books|music|spotify)\b", re.IGNORECASE)
NEWER_STANDARD_LIBRARY = {"tomllib"}
FILTER_BANNED = (
    "dataclasses",
    "inspect",
    "zipfile",
    "urllib",
    "xml",
    "http",
    "subprocess",
    "pytest",
    "hoard.testing",
    "hoard.build",
    "hoard.new",
    "hoard._index",
    "hoard._doctor",
    "hoard._system",
    "hoard._oracle",
    "hoard._embedder",
)


def library_sources():
    return sorted(PACKAGE.rglob("*.py"))


def top_level(name: str) -> str:
    return name.split(".")[0]


def is_standard_library(name: str) -> bool:
    if name in NEWER_STANDARD_LIBRARY:
        return True
    if hasattr(sys, "stdlib_module_names"):
        return name in sys.stdlib_module_names
    if name in sys.builtin_module_names:
        return True
    spec = importlib.util.find_spec(name)
    origin = (spec.origin or "") if spec else ""
    return origin.startswith(sysconfig.get_paths()["stdlib"]) and "site-packages" not in origin


def allowed_third_party(path: Path) -> set:
    subpackage = path.relative_to(PACKAGE).parts[0]
    return DEV_ONLY.get(subpackage, set())


@pytest.mark.parametrize("path", library_sources(), ids=lambda p: str(p.relative_to(PACKAGE)))
def test_library_imports_only_itself_and_the_standard_library(path):
    outside = {
        top_level(name)
        for name in imported_names(str(path))
        if top_level(name) != "hoard" and not is_standard_library(top_level(name))
    }
    assert outside <= allowed_third_party(path), f"{path.name} should import only hoard and the standard library"


@pytest.mark.parametrize("path", sorted(PACKAGE.rglob("*")), ids=lambda p: str(p.relative_to(PACKAGE)))
def test_library_names_no_kind(path):
    if path.is_dir() or path.suffix in (".png", ".pyc"):
        return
    assert not KIND_NAMES.search(path.read_text(encoding="utf-8")), f"{path.name} should not know any kind by name"


def test_private_modules_carry_an_underscore():
    modules = {p.stem for p in PACKAGE.glob("*.py")}
    folders = {p.name for p in PACKAGE.iterdir() if p.is_dir() and p.name != "__pycache__"}
    assert {m for m in modules - PUBLIC if not m.startswith("_")} == set(), "only the public surface goes unprefixed"
    assert folders == SUBPACKAGES, "the library should grow no folders beyond render, testing, build and template"


def lean_kind(folder: Path) -> str:
    (folder / "lean_kind.py").write_text(
        "from hoard.contract import Kind, Storage, lazy, roots_from\n"
        "KIND = Kind(name='lean', keyword='ln', fields=('path',), evidence=str,\n"
        "            storages=(Storage('shelf', roots_from('shelf'), lazy('zipfile', 'is_zipfile')),))\n"
    )
    return "lean_kind"


def test_filter_mode_loads_only_the_keystroke_path(tmp_path):
    module = lean_kind(tmp_path)
    probe = (
        "import json, sys\n"
        "from hoard.cli import main\n"
        f"main({module!r}, ['filter', 'anything'])\n"
        "print(json.dumps(sorted(sys.modules)), file=sys.stderr)\n"
    )
    environ = dict(
        os.environ,
        PYTHONPATH=os.pathsep.join([str(tmp_path), str(PACKAGE.parent)]),
        alfred_workflow_data=str(tmp_path / "data"),
        alfred_workflow_cache=str(tmp_path / "cache"),
    )
    finished = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, env=environ, check=True)
    loaded = json.loads(finished.stderr.strip().splitlines()[-1])
    banned = sorted(m for m in loaded if any(m == b or m.startswith(b + ".") for b in FILTER_BANNED))
    assert banned == [], "a keystroke should load SQLite and the renderer only"
    assert json.loads(finished.stdout)["items"][0]["title"] == "Index is empty", "the lean kind should still answer"
