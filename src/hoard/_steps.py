from __future__ import annotations

import filecmp
import os
import shutil
import sys
import unicodedata
from typing import Optional, Sequence

from hoard._fold import under
from hoard._plan import MOVES, TRASH, describe
from hoard.contract import STEP_VERBS, Change, Context, Kind, Step

RENAMING = ".hoard-renaming"


def settled(path: str) -> Optional[str]:
    folder, name = os.path.split(path)
    return None if name in ("", ".", "..") else os.path.join(os.path.realpath(folder), name)


def real_roots(ctx: Context) -> list:
    return [os.path.realpath(root) for roots in ctx.roots.values() for root in roots]


def ground_of(kind: Kind, ctx: Context) -> list:
    wider = [os.path.realpath(folder) for folder in kind.ground(ctx)] if kind.ground else []
    return wider + real_roots(ctx)


def root_of(path: str, ground: Sequence[str]) -> Optional[str]:
    return next((root for root in ground if under(path, root)), None)


def nfc(name: str) -> str:
    return unicodedata.normalize("NFC", name)


def likeness(entry: str, name: str, composed: str, folded: str) -> int:
    if entry == name:
        return 0
    if nfc(entry) == composed:
        return 1
    return 2 if nfc(entry).casefold() == folded else 3


def child_named(folder: str, name: str) -> Optional[str]:
    try:
        entries = os.listdir(folder)
    except OSError:
        return None
    composed = nfc(name)
    ranked = sorted((likeness(entry, name, composed, composed.casefold()), entry) for entry in entries)
    return os.path.join(folder, ranked[0][1]) if ranked and ranked[0][0] < 3 else None


def located(root: str, path: str) -> Optional[str]:
    current: Optional[str] = root
    for part in os.path.relpath(path, root).split(os.sep):
        current = child_named(current, part) if current else None
    return current


def respell(path: str, name: str) -> str:
    target = os.path.join(os.path.dirname(path), name)
    if os.path.basename(path) == name:
        return path
    temporary = target + RENAMING
    os.rename(path, temporary)
    os.rename(temporary, target)
    return target


def settle_parents(root: str, target: str) -> str:
    current = root
    for part in os.path.relpath(os.path.dirname(target), root).split(os.sep):
        if part == ".":
            continue
        found = child_named(current, part)
        current = respell(found, part) if found else os.path.join(current, part)
        os.makedirs(current, exist_ok=True)
    return current


def numbered(path: str, n: int) -> str:
    stem, extension = os.path.splitext(path)
    return f"{stem} ({n}){extension}"


def unique(path: str) -> str:
    candidates = (path if n == 1 else numbered(path, n) for n in range(1, 10_000))
    return next(candidate for candidate in candidates if not os.path.lexists(candidate))


def trash_path(before: str, root: str) -> str:
    return unique(os.path.join(root, TRASH, os.path.relpath(before, root)))


def target_of(step: Step, ground: Sequence[str]) -> Optional[str]:
    if step.verb == "trash":
        return trash_path(step.before, root_of(step.before, ground))
    after = settled(step.after) if step.after else None
    return after if after and root_of(after, ground) else None


def same_file(a: str, b: str) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def empty_folder(path: str) -> bool:
    return os.path.isdir(path) and not os.listdir(path)


def redundant(source: str, existing: str) -> bool:
    if empty_folder(source):
        return os.path.isdir(existing)
    return os.path.isfile(source) and os.path.isfile(existing) and filecmp.cmp(source, existing, shallow=False)


def blocked(before: str, target: str) -> bool:
    return os.path.lexists(target) and not same_file(before, target)


def prune_empty(folder: str, root: Optional[str]) -> None:
    while root and folder != root and under(folder, root) and os.path.isdir(folder) and not os.listdir(folder):
        os.rmdir(folder)
        folder = os.path.dirname(folder)


def remove(path: str, root: str) -> None:
    os.rmdir(path) if os.path.isdir(path) else os.remove(path)
    prune_empty(os.path.dirname(path), root)


def copy(source: str, target: str) -> bool:
    if not os.path.isfile(source):
        return False
    shutil.copy2(source, target)
    return True


def move(source: str, target: str, root: str) -> None:
    if os.path.dirname(source) == os.path.dirname(target):
        respell(source, os.path.basename(target))
    else:
        os.rename(source, target)
    prune_empty(os.path.dirname(source), root)


def source_of(step: Step, ground: Sequence[str]) -> Optional[str]:
    before = settled(step.before)
    root = root_of(before, ground) if before and step.verb in STEP_VERBS else None
    return located(root, before) if root else None


def landing(step: Step, source: str, ground: Sequence[str]) -> tuple:
    wanted = target_of(step._replace(before=source), ground)
    if wanted is None:
        return None, None
    parent = settle_parents(root_of(wanted, ground), wanted)
    return os.path.join(parent, os.path.basename(wanted)), child_named(parent, os.path.basename(wanted))


def apply_step(step: Step, ctx: Context, ground: Optional[Sequence[str]] = None) -> Optional[Change]:
    ground = ground or real_roots(ctx)
    source = source_of(step, ground)
    if source is None:
        return None
    target, existing = landing(step, source, ground)
    if target is None:
        return None
    root = root_of(source, ground)
    on_disk = located(root, source) or source
    if existing is not None and not same_file(on_disk, existing):
        if step.verb in MOVES and redundant(on_disk, existing):
            remove(on_disk, root)
            return Change(step.id, "delete", source, existing)
        return None
    if step.verb == "copy":
        return Change(step.id, "copy", source, target) if not existing and copy(on_disk, target) else None
    move(on_disk, target, root)
    return Change(step.id, step.verb, source, target)


def escorted(change: Change, kind: Kind, ctx: Context, back: bool = False) -> None:
    if kind.escort and change.kind_of_change in MOVES:
        kind.escort(*((change.after, change.before) if back else (change.before, change.after)), ctx)


def attempted(step: Step, kind: Kind, ctx: Context, ground: Sequence[str]) -> Optional[Change]:
    try:
        change = apply_step(step, ctx, ground)
        if change:
            escorted(change, kind, ctx)
        return change
    except OSError as error:
        print(f"apply: {describe(step)}: {error!r}", file=sys.stderr)
        return None


def carry_out(steps, kind: Kind, ctx: Context) -> list:
    ground = ground_of(kind, ctx)
    return [change for change in (attempted(step, kind, ctx, ground) for step in steps) if change]


def restorable(change: Change) -> bool:
    return os.path.lexists(change.after) and not blocked(change.after, change.before)


def restore(change: Change, ground: Sequence[str]) -> None:
    root = root_of(change.before, ground)
    parent = settle_parents(root, change.before) if root else os.path.dirname(change.before)
    os.makedirs(parent, exist_ok=True)
    move(change.after, os.path.join(parent, os.path.basename(change.before)), root_of(change.after, ground))


def uncopy(change: Change, ground: Sequence[str]) -> None:
    if os.path.isfile(change.after) and not same_file(change.before, change.after):
        remove(change.after, root_of(change.after, ground))


def bring_back(change: Change) -> None:
    if os.path.isdir(change.after):
        os.makedirs(change.before, exist_ok=True)
    else:
        os.makedirs(os.path.dirname(change.before), exist_ok=True)
        shutil.copy2(change.after, change.before)


def undo_change(change: Change, ground: Sequence[str]) -> bool:
    if change.kind_of_change == "copy":
        uncopy(change, ground)
        return False
    if change.kind_of_change == "delete":
        if not os.path.lexists(change.before):
            bring_back(change)
        return False
    if restorable(change):
        restore(change, ground)
        return True
    print(f"undo: kept {change.after}, {change.before} is taken or {change.after} is gone", file=sys.stderr)
    return False


def undo_changes(changes, kind: Kind, ctx: Context) -> None:
    ground = ground_of(kind, ctx)
    for change in reversed(list(changes)):
        try:
            if undo_change(change, ground):
                escorted(change, kind, ctx, back=True)
        except OSError as error:
            print(f"undo: {change.after} → {change.before}: {error!r}", file=sys.stderr)
