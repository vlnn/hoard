from __future__ import annotations

import os
import plistlib
from typing import MutableMapping

DATA = "Library/Application Support/Alfred/Workflow Data"
CACHE = "Library/Caches/com.runningwithcrayons.Alfred/Workflow Data"


def read_plist(path: str) -> dict:
    try:
        with open(path, "rb") as handle:
            return plistlib.load(handle)
    except (OSError, plistlib.InvalidFileException):
        return {}


def alfred_folders(bundleid: str, home: str) -> dict:
    return {
        "alfred_workflow_bundleid": bundleid,
        "alfred_workflow_data": os.path.join(home, DATA, bundleid),
        "alfred_workflow_cache": os.path.join(home, CACHE, bundleid),
    }


def fill_from_workflow(folder: str, environ: MutableMapping[str, str]) -> None:
    bundleid = read_plist(os.path.join(folder, "info.plist")).get("bundleid")
    if not bundleid:
        return
    found = alfred_folders(bundleid, environ.get("HOME", os.path.expanduser("~")))
    found.update({key: str(value) for key, value in read_plist(os.path.join(folder, "prefs.plist")).items()})
    for key, value in found.items():
        environ.setdefault(key, value)
