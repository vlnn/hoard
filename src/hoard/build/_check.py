from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from hoard.build._bundle import bundle
from hoard.build._workflow import BuildError, Workflow, read_workflow

EXPECTED = "Index is empty"


def bundle_environment(scratch: Path) -> dict:
    environ = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    environ.update(alfred_workflow_data=str(scratch / "data"), alfred_workflow_cache=str(scratch / "cache"))
    return environ


def titles(output: str) -> list:
    try:
        return [item["title"] for item in json.loads(output)["items"]]
    except (ValueError, KeyError, TypeError) as error:
        raise BuildError(f"the filter printed no rows: {output!r}") from error


def answer_empty_query(workflow_folder: Path, scratch: Path) -> list:
    finished = subprocess.run(
        [sys.executable, "-I", "hoard.py", "filter", ""],
        cwd=workflow_folder,
        env=bundle_environment(scratch),
        capture_output=True,
        text=True,
    )
    if finished.returncode != 0:
        raise BuildError(f"the bundle's filter failed:\n{finished.stderr}")
    return titles(finished.stdout)


def import_package(workflow: Workflow, workflow_folder: Path, scratch: Path) -> str:
    finished = subprocess.run(
        [sys.executable, "-I", "-c", f"import sys; sys.path.insert(0, {str(workflow_folder)!r}); import {workflow.kind}"],
        cwd=workflow_folder,
        env=bundle_environment(scratch),
        capture_output=True,
        text=True,
    )
    if finished.returncode != 0:
        raise BuildError(f"the bundle cannot import {workflow.kind}:\n{finished.stderr}")
    return f"ok: {workflow.kind} imports"


def answers(workflow_folder: Path, scratch: Path) -> str:
    answered = answer_empty_query(workflow_folder, scratch)
    if EXPECTED not in answered:
        raise BuildError(f"an empty database should answer {EXPECTED!r}, got {answered!r}")
    return f"ok: {EXPECTED}"


def check(repo=".") -> str:
    workflow = read_workflow(Path(repo).resolve())
    archive_path = bundle(repo)
    with tempfile.TemporaryDirectory() as scratch:
        workflow_folder = Path(scratch) / "workflow"
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(workflow_folder)
        if workflow.handmade:
            return import_package(workflow, workflow_folder, Path(scratch))
        return answers(workflow_folder, Path(scratch))
