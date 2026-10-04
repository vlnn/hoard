from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from hoard import new

LIBRARY = Path(__file__).resolve().parents[1]

EXPECTED_FILES = {
    ".gitignore",
    ".python-version",
    "Makefile",
    "README.md",
    "pyproject.toml",
    "shelf/__init__.py",
    "tests/conftest.py",
    "tests/test_conformance.py",
    "workflow/icon.png",
    "workflow/plist.toml",
}


@pytest.fixture
def generated(tmp_path):
    return new.write_kind_repository("shelf", tmp_path / "repos", keyword="sh", hoard_source=LIBRARY)


def relative_files(root: Path) -> set:
    return {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}


def test_template_writes_the_kind_repository_layout(generated):
    assert generated.name == "hoard-shelf", "the repository should be named after the kind"
    assert relative_files(generated) == EXPECTED_FILES, "the template should write exactly the kind layout"


@pytest.mark.parametrize(
    "relative, fragment",
    [
        ("pyproject.toml", 'name = "hoard-shelf"'),
        ("shelf/__init__.py", 'keyword="sh"'),
        ("shelf/__init__.py", 'name="shelf"'),
        ("workflow/plist.toml", 'bundleid = "com.example.hoard.shelf"'),
        ("workflow/plist.toml", 'name = "Shelf"'),
        ("tests/conftest.py", 'pytest_plugins = ["hoard.testing"]'),
        ("tests/test_conformance.py", "from shelf import KIND"),
        ("Makefile", "\tuv run pytest"),
        ("Makefile", "$(SYSTEM_PYTHON)"),
    ],
)
def test_template_fills_in_the_kind(generated, relative, fragment):
    assert fragment in (generated / relative).read_text(), f"{relative} should contain {fragment!r}"


def test_the_path_dependency_points_at_the_library(generated):
    line = next(l for l in (generated / "pyproject.toml").read_text().splitlines() if l.startswith("hoard = "))
    relative = line.split('"')[1]
    assert (generated / relative / "src" / "hoard").is_dir(), "the path dependency should resolve to the library"


def test_refuses_to_write_over_an_existing_repository(generated):
    with pytest.raises(FileExistsError):
        new.write_kind_repository("shelf", generated.parent, hoard_source=LIBRARY)


@pytest.mark.parametrize("name", ["Shelf", "my-shelf", "1shelf", ""])
def test_rejects_names_that_cannot_be_a_module(tmp_path, name):
    with pytest.raises(ValueError):
        new.write_kind_repository(name, tmp_path, hoard_source=LIBRARY)


def test_generated_repository_passes_its_conformance_and_builds(generated):
    pytest.importorskip("tomllib")
    environ = dict(os.environ, PYTHONPATH=os.pathsep.join([str(LIBRARY / "src"), str(generated)]))
    suite = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=generated, env=environ, capture_output=True, text=True)
    assert suite.returncode == 0, f"a fresh kind should pass the shipped suite:\n{suite.stdout}{suite.stderr}"
    build = subprocess.run([sys.executable, "-m", "hoard.build", "--check"], cwd=generated, env=environ, capture_output=True, text=True)
    assert build.returncode == 0, f"a fresh kind should build and answer a keystroke:\n{build.stdout}{build.stderr}"
    assert (generated / "dist" / "shelf.alfredworkflow").is_file(), "the build should leave a bundle in dist/"
