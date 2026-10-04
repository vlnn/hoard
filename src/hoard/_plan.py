from __future__ import annotations

import json
import os
from typing import Optional

from hoard._fold import under
from hoard.contract import STEP_VERBS, Change, Context, Step

TRASH = ".hoard-trash"
PREFIX = "step:"


def encode(step: Step) -> str:
    return PREFIX + json.dumps(list(step), ensure_ascii=False)


def decode(text: str) -> Step:
    return Step(*json.loads(text[len(PREFIX) :]))


def root_of(path: str, ctx: Context) -> Optional[str]:
    return next((root for roots in ctx.roots.values() for root in roots if under(path, root)), None)


def numbered(path: str, n: int) -> str:
    stem, extension = os.path.splitext(path)
    return f"{stem} ({n}){extension}"


def unique(path: str) -> str:
    candidates = (path if n == 1 else numbered(path, n) for n in range(1, 10_000))
    return next(candidate for candidate in candidates if not os.path.lexists(candidate))


def trash_path(before: str, root: str) -> str:
    return unique(os.path.join(root, TRASH, os.path.relpath(before, root)))


def target_of(step: Step, ctx: Context) -> Optional[str]:
    root = root_of(step.before, ctx)
    if root is None:
        return None
    if step.verb == "trash":
        return trash_path(step.before, root)
    return step.after if step.after and under(step.after, root) else None


def blocked(before: str, target: str) -> bool:
    return os.path.lexists(target) and not os.path.samefile(before, target)


def apply_step(step: Step, ctx: Context) -> Optional[Change]:
    if step.verb not in STEP_VERBS or not os.path.lexists(step.before):
        return None
    target = target_of(step, ctx)
    if target is None or blocked(step.before, target):
        return None
    os.makedirs(os.path.dirname(target), exist_ok=True)
    os.rename(step.before, target)
    prune_empty(os.path.dirname(step.before), root_of(step.before, ctx))
    return Change(step.id, step.verb, step.before, target)


def prune_empty(folder: str, root: Optional[str]) -> None:
    while root and folder != root and under(folder, root) and os.path.isdir(folder) and not os.listdir(folder):
        os.rmdir(folder)
        folder = os.path.dirname(folder)


def undo_changes(changes, ctx: Context) -> None:
    for change in reversed(list(changes)):
        os.makedirs(os.path.dirname(change.before), exist_ok=True)
        os.rename(change.after, change.before)
        prune_empty(os.path.dirname(change.after), root_of(change.after, ctx))


def name_of(change: Change) -> str:
    return os.path.basename(change.after if change.kind_of_change == "move" else change.before)


def describe(step: Step) -> str:
    moved = f" → {step.after}" if step.verb == "move" else ""
    return f"{step.verb:<6} {step.before}{moved}  ({step.reason})"


def step_title(step: Step) -> str:
    return os.path.basename(step.after if step.verb == "move" else step.before)


def step_subtitle(step: Step) -> str:
    where = f"from {os.path.basename(step.before)}" if step.verb == "move" else "to the trash"
    return f"{step.reason} · {where}"
