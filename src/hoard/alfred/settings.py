from __future__ import annotations

import os
from typing import Mapping

ON = frozenset({"1", "true", "yes", "on"})


def is_on(value: str) -> bool:
    return value.strip().lower() in ON


def fallback_folder(environ: Mapping[str, str], base_variable: str, default: str, name: str) -> str:
    base = environ.get(base_variable) or os.path.expanduser(default)
    return os.path.join(base, "hoard", name)


def data_folder(environ: Mapping[str, str], name: str) -> str:
    return environ.get("alfred_workflow_data") or fallback_folder(environ, "XDG_DATA_HOME", "~/.local/share", name)


def cache_folder(environ: Mapping[str, str], name: str) -> str:
    return environ.get("alfred_workflow_cache") or fallback_folder(environ, "XDG_CACHE_HOME", "~/.cache", name)
