from __future__ import annotations

import os
from typing import Mapping

from hoard.contract import Context, Kind


def fallback_folder(environ: Mapping[str, str], base_variable: str, default: str, name: str) -> str:
    base = environ.get(base_variable) or os.path.expanduser(default)
    return os.path.join(base, "hoard", name)


def data_folder(kind: Kind, environ: Mapping[str, str]) -> str:
    return environ.get("alfred_workflow_data") or fallback_folder(environ, "XDG_DATA_HOME", "~/.local/share", kind.name)


def cache_folder(kind: Kind, environ: Mapping[str, str]) -> str:
    return environ.get("alfred_workflow_cache") or fallback_folder(environ, "XDG_CACHE_HOME", "~/.cache", kind.name)


def from_environ(kind: Kind, environ: Mapping[str, str] = os.environ) -> Context:
    data, cache = data_folder(kind, environ), cache_folder(kind, environ)
    os.makedirs(data, exist_ok=True)
    os.makedirs(cache, exist_ok=True)
    return Context(data=data, cache=cache, config=dict(environ))
