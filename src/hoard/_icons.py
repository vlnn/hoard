from __future__ import annotations

import os
from typing import Optional

from hoard.contract import Entity, Kind

SIGNATURES = (
    (b"\xff\xd8\xff", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"GIF8", ".gif"),
)


def image_suffix(data: bytes) -> Optional[str]:
    return next((suffix for magic, suffix in SIGNATURES if data.startswith(magic)), None)


def write_once(path: str, data: bytes) -> str:
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(data)
    return path


def cached_cover(entity: Entity, cache: str) -> Optional[str]:
    suffix = image_suffix(entity.cover)
    if suffix is None:
        return None
    return write_once(os.path.join(cache, "icons", entity.id + suffix), entity.cover)


def icon_for(kind: Kind, entity: Entity, cache: str) -> Optional[str]:
    return cached_cover(entity, cache) or kind.icon(entity)
