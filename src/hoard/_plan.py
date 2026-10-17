from __future__ import annotations

import json
import os

from hoard.contract import Change, Step

TRASH = ".hoard-trash"
PREFIX = "step:"
MOVES = frozenset({"move", "trash"})
ARRIVALS = frozenset({"move", "copy"})


def encode(step: Step) -> str:
    return PREFIX + json.dumps(list(step), ensure_ascii=False)


def decode(text: str) -> Step:
    return Step(*json.loads(text[len(PREFIX) :]))


def name_of(change: Change) -> str:
    return os.path.basename(change.after if change.kind_of_change in ARRIVALS else change.before)


def describe(step: Step) -> str:
    moved = f" → {step.after}" if step.verb in ARRIVALS else ""
    return f"{step.verb:<6} {step.before}{moved}  ({step.reason})"


def step_title(step: Step) -> str:
    return os.path.basename(step.after if step.verb in ARRIVALS else step.before)


def step_subtitle(step: Step) -> str:
    where = {"move": "from", "copy": "copy of"}.get(step.verb)
    origin = f"{where} {os.path.basename(step.before)}" if where else "to the trash"
    return f"{step.reason} · {origin}"
