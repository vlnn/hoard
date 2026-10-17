from __future__ import annotations

import json
import plistlib
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import NamedTuple, Optional

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


class KindFacts(NamedTuple):
    keyword: str
    roles: tuple


def kind_facts(repo: Path, kind: str) -> KindFacts:
    probe = f"import json, {kind}; from hoard import _models; k = {kind}.KIND; print(json.dumps([k.keyword, _models.roles_of(k)]))"
    finished = subprocess.run([sys.executable, "-c", probe], cwd=repo, capture_output=True, text=True)
    if finished.returncode != 0:
        raise BuildError(f"cannot import {kind}.KIND from {repo}:\n{finished.stderr}")
    keyword, roles = json.loads(finished.stdout)
    return KindFacts(keyword, tuple(roles))


def versions(repo: Path, kind: str) -> dict:
    return {"hoard": hoard.__version__, kind: kind_version(repo)}


IDENTITY = ("name", "bundleid", "description", "createdby")


def stamped(repo: Path, workflow: Workflow) -> dict:
    with open(repo / workflow.plist, "rb") as handle:
        plist = plistlib.load(handle)
    plist.update({key: value for key in IDENTITY if (value := getattr(workflow, key))})
    plist["version"] = kind_version(repo)
    return plist


def generated(repo: Path, workflow: Workflow) -> dict:
    facts = kind_facts(repo, workflow.kind)
    return info_plist(workflow, facts.keyword, kind_version(repo), facts.roles)


def write_static(target: Path, repo: Path, workflow: Workflow) -> None:
    plist = stamped(repo, workflow) if workflow.handmade else generated(repo, workflow)
    with open(target / "info.plist", "wb") as handle:
        plistlib.dump(plist, handle)
    if not workflow.handmade:
        (target / "hoard.py").write_text(ENTRY.format(kind=workflow.kind), encoding="utf-8")
    (target / "version.json").write_text(json.dumps(versions(repo, workflow.kind), indent=2) + "\n", encoding="utf-8")


def skip_development(folder: str, names: list) -> set:
    ignored = {name for name in names if name == "__pycache__" or name.endswith(".pyc")}
    if Path(folder).resolve() == library_package():
        ignored |= DEVELOPMENT_ONLY & set(names)
    return ignored


def asset_paths(repo: Path, workflow: Workflow) -> list:
    standard = [repo / "workflow" / "icon.png", repo / "workflow" / "icons"]
    return [path for path in standard + [repo / asset for asset in workflow.assets] if path.exists()]


def copy_asset(source: Path, target: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, target / source.name)
    else:
        shutil.copyfile(source, target / source.name)


def stage(repo: Path, workflow: Workflow, target: Path) -> None:
    write_static(target, repo, workflow)
    for asset in asset_paths(repo, workflow):
        copy_asset(asset, target)
    shutil.copytree(library_package(), target / "hoard", ignore=skip_development)
    shutil.copytree(workflow.package(repo), target / workflow.kind, ignore=skip_development)


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
