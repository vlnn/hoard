from __future__ import annotations

import hashlib
import os
import shutil
from typing import Optional

from hoard.contract import Change, Command, Entity, Kind, Plan, Step, Storage, Verb, roots_from

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


def packing_target(found, satchel_root: str) -> Optional[tuple]:
    source = found.locator_in("shelf")
    if found.on("satchel") or source is None:
        return None
    target = os.path.join(satchel_root, os.path.basename(source))
    return None if os.path.exists(target) else (source, target)


def pack(founds, ctx) -> list:
    roots = ctx.roots_of("satchel")
    if not roots:
        return []
    changes = []
    for found in founds:
        paths = packing_target(found, roots[0])
        if paths:
            os.makedirs(roots[0], exist_ok=True)
            shutil.copyfile(*paths)
            changes.append(Change(found.entity.id, "copy", *paths))
    return changes


def unpack(changes, ctx) -> None:
    for change in changes:
        os.remove(change.after)


def toss(founds, ctx) -> list:
    return [Change(found.entity.id, "toss", None, None) for found in founds]


def canonical_steps(found) -> list:
    path = found.locator_in("shelf")
    if path is None:
        return []
    target = os.path.join(os.path.dirname(path), found.entity.title + SUFFIX)
    return [] if os.path.basename(path) == os.path.basename(target) else [Step("move", found.entity.id, path, target, "canonical name")]


def junk_files(root: str) -> list:
    found = []
    for folder, folders, files in os.walk(root):
        folders[:] = sorted(name for name in folders if not name.startswith("."))
        found += [os.path.join(folder, name) for name in sorted(files) if name.endswith(".tmp")]
    return found


def lint(founds, ctx) -> Plan:
    renames = [step for found in founds for step in canonical_steps(found)]
    junk = [Step("trash", "", path, None, "junk") for root in ctx.roots_of("shelf") for path in junk_files(root)]
    return Plan(tuple(renames + junk))


KIND = Kind(
    name="fake",
    keyword="fk",
    storages=(
        Storage("shelf", roots_from("fake_shelf"), read_note),
        Storage("satchel", roots_from("fake_satchel"), read_note),
    ),
    fields=("author", "year", "path"),
    evidence=evidence,
    verbs={"pack": Verb("Pack into the satchel", pack, unpack), "toss": Verb("Toss", toss)},
    commands={"loose": Command("Pack", "pack", off=("satchel",))},
    lint=lint,
    labels={"one": "note", "many": "notes"},
)
