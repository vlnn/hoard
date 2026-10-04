from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from hoard.build._bundle import bundle
from hoard.build._workflow import BuildError

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


def check(repo=".") -> str:
    archive_path = bundle(repo)
    with tempfile.TemporaryDirectory() as scratch:
        workflow_folder = Path(scratch) / "workflow"
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(workflow_folder)
        answered = answer_empty_query(workflow_folder, Path(scratch))
    if EXPECTED not in answered:
        raise BuildError(f"an empty database should answer {EXPECTED!r}, got {answered!r}")
    return f"ok: {EXPECTED}"
