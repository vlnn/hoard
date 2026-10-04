from __future__ import annotations

import subprocess
from typing import Optional

from hoard._fold import Row

SYSTEM_VERBS = {
    "open": (("open",), "Opened"),
    "reveal": (("open", "-R"), "Revealed"),
}


def reachable_target(row: Row) -> Optional[tuple]:
    nearest = row.found.nearest
    if nearest is None or not nearest.reachable or not nearest.locator:
        return None
    return row.found.entity.title, nearest.locator


def reachable_locators(rows: list) -> list:
    return [target for target in map(reachable_target, rows) if target]


def report(past: str, verb: str, titles: list) -> str:
    if not titles:
        return f"Nothing to {verb}"
    if len(titles) == 1:
        return f"{past} {titles[0]}"
    return f"{past} {len(titles)} items"


def hand_over(rows: list, verb: str) -> str:
    command, past = SYSTEM_VERBS[verb]
    targets = reachable_locators(rows)
    for _, locator in targets:
        subprocess.run([*command, locator], check=False)
    return report(past, verb, [title for title, _ in targets])
