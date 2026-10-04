from __future__ import annotations

import hashlib
import os
from typing import Optional

from hoard.contract import Entity, Kind, Storage, roots_from

SUFFIX = ".note"


def fingerprint(data: bytes) -> str:
    return hashlib.blake2b(data, digest_size=16).hexdigest()


def stem(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0]


def parse_headers(headers: str) -> dict:
    pairs = (line.split(":", 1) for line in headers.splitlines() if ":" in line)
    return {key.strip(): value.strip() for key, value in pairs}


def read_note(path: str) -> Optional[Entity]:
    if not path.endswith(SUFFIX):
        return None
    with open(path, "rb") as handle:
        data = handle.read()
    headers, _, body = data.decode("utf-8").partition("\n\n")
    values = parse_headers(headers)
    return Entity(
        id=fingerprint(data),
        title=values.get("title") or stem(path),
        fields=(values.get("author", ""), values.get("year", ""), path),
        text=body,
    )


def note_text(title: str, author: str = "", year: str = "", body: str = "") -> str:
    return f"title: {title}\nauthor: {author}\nyear: {year}\n\n{body}"


def write_note(root, name: str, title: str, author: str = "", year: str = "", body: str = "", mtime=None) -> str:
    path = os.path.join(str(root), name + SUFFIX)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(note_text(title, author, year, body))
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def evidence(entity: Entity) -> str:
    return "\n".join((entity.title, *entity.fields[:2], entity.text))


KIND = Kind(
    name="fake",
    keyword="fk",
    storages=(
        Storage("shelf", roots_from("fake_shelf"), read_note),
        Storage("satchel", roots_from("fake_satchel"), read_note),
    ),
    fields=("author", "year", "path"),
    evidence=evidence,
)
