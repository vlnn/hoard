from __future__ import annotations

import os
from typing import Mapping

from hoard.alfred.settings import cache_folder, data_folder
from hoard.contract import Context, Kind


def from_environ(kind: Kind, environ: Mapping[str, str] = os.environ) -> Context:
    data, cache = data_folder(environ, kind.name), cache_folder(environ, kind.name)
    os.makedirs(data, exist_ok=True)
    os.makedirs(cache, exist_ok=True)
    return Context(data=data, cache=cache, config=dict(environ))
