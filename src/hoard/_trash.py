from __future__ import annotations

import os

from hoard._fold import ground_of
from hoard.contract import TRASH, Context, Kind

UNITS = ("B", "KB", "MB", "GB", "TB")


def folders(kind: Kind, ctx: Context) -> list:
    candidates = (os.path.join(folder, TRASH) for folder in ground_of(kind, ctx))
    return [folder for folder in candidates if os.path.isdir(folder)]


def sizes(folder: str):
    for here, _, files in os.walk(folder):
        for name in files:
            try:
                yield os.stat(os.path.join(here, name)).st_size
            except OSError:
                continue


def contents(kind: Kind, ctx: Context) -> tuple:
    found = [size for folder in folders(kind, ctx) for size in sizes(folder)]
    return len(found), sum(found)


def human(size: int) -> str:
    amount, unit = float(size), UNITS[0]
    for unit in UNITS:
        if amount < 1000 or unit == UNITS[-1]:
            break
        amount /= 1024
    return f"{round(amount)} {unit}" if unit == UNITS[0] else f"{amount:.1f} {unit}"


def empty(kind: Kind, ctx: Context) -> int:
    import shutil

    count, _ = contents(kind, ctx)
    for folder in folders(kind, ctx):
        shutil.rmtree(folder, ignore_errors=True)
    return count
