from __future__ import annotations

import json
import plistlib
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

import hoard
from hoard.build._plist import info_plist
from hoard.build._workflow import BuildError, Workflow, kind_version, read_workflow

DEVELOPMENT_ONLY = {"testing", "build", "template", "new.py"}

ENTRY = """import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hoard.cli import main

main({kind!r})
"""


def library_package() -> Path:
    return Path(hoard.__file__).resolve().parent


def kind_keyword(repo: Path, kind: str) -> str:
    probe = f"import {kind}; print({kind}.KIND.keyword)"
    finished = subprocess.run([sys.executable, "-c", probe], cwd=repo, capture_output=True, text=True)
    if finished.returncode != 0:
        raise BuildError(f"cannot import {kind}.KIND from {repo}:\n{finished.stderr}")
    return finished.stdout.strip()


def versions(repo: Path, kind: str) -> dict:
    return {"hoard": hoard.__version__, kind: kind_version(repo)}


def write_static(target: Path, repo: Path, workflow: Workflow) -> None:
    keyword = kind_keyword(repo, workflow.kind)
    plist = info_plist(workflow, keyword, kind_version(repo))
    with open(target / "info.plist", "wb") as handle:
        plistlib.dump(plist, handle)
    (target / "hoard.py").write_text(ENTRY.format(kind=workflow.kind), encoding="utf-8")
    (target / "version.json").write_text(json.dumps(versions(repo, workflow.kind), indent=2) + "\n", encoding="utf-8")


def skip_development(folder: str, names: list) -> set:
    ignored = {name for name in names if name == "__pycache__" or name.endswith(".pyc")}
    if Path(folder).resolve() == library_package():
        ignored |= DEVELOPMENT_ONLY & set(names)
    return ignored


def copy_assets(repo: Path, target: Path) -> None:
    assets = repo / "workflow"
    shutil.copyfile(assets / "icon.png", target / "icon.png")
    if (assets / "icons").is_dir():
        shutil.copytree(assets / "icons", target / "icons")


def stage(repo: Path, workflow: Workflow, target: Path) -> None:
    write_static(target, repo, workflow)
    copy_assets(repo, target)
    shutil.copytree(library_package(), target / "hoard", ignore=skip_development)
    shutil.copytree(repo / workflow.kind, target / workflow.kind, ignore=skip_development)


def zip_folder(folder: Path, archive_path: Path) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                archive.write(path, str(path.relative_to(folder)))


def bundle(repo=".", out: Optional[Path] = None) -> Path:
    repo = Path(repo).resolve()
    workflow = read_workflow(repo)
    archive_path = Path(out or repo / "dist") / f"{workflow.kind}.alfredworkflow"
    with tempfile.TemporaryDirectory() as scratch:
        stage(repo, workflow, Path(scratch))
        zip_folder(Path(scratch), archive_path)
    return archive_path
