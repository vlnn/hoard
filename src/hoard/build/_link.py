from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from hoard.build._bundle import library_package, write_static
from hoard.build._workflow import BuildError, read_workflow

ALFRED = Path("~/Library/Application Support/Alfred").expanduser()


def alfred_workflows_folder() -> Path:
    prefs = ALFRED / "prefs.json"
    if prefs.is_file():
        return Path(json.loads(prefs.read_text())["current"]) / "workflows"
    default = ALFRED / "Alfred.alfredpreferences" / "workflows"
    if default.is_dir():
        return default
    raise BuildError("cannot find Alfred's preferences; pass --into with its workflows folder")


def replace_symlink(link: Path, target: Path) -> None:
    if link.is_symlink() or link.is_file():
        link.unlink()
    os.symlink(target, link)


def link(repo=".", into: Optional[Path] = None) -> Path:
    repo = Path(repo).resolve()
    workflow = read_workflow(repo)
    installed = Path(into or alfred_workflows_folder()) / f"user.workflow.{workflow.bundleid}"
    installed.mkdir(parents=True, exist_ok=True)
    write_static(installed, repo, workflow)
    replace_symlink(installed / "hoard", library_package())
    replace_symlink(installed / workflow.kind, repo / workflow.kind)
    replace_symlink(installed / "icon.png", repo / "workflow" / "icon.png")
    if (repo / "workflow" / "icons").is_dir():
        replace_symlink(installed / "icons", repo / "workflow" / "icons")
    return installed
