from __future__ import annotations

import os
import platform
import sqlite3
import sys
from dataclasses import dataclass

from hoard import _db
from hoard.contract import Context, Kind, Storage

LABELS = {"ok": "ok", "warn": "warn", "fail": "FAIL"}
FLOOR = (3, 9)


@dataclass(frozen=True)
class Check:
    name: str
    value: str
    status: str


@dataclass(frozen=True)
class Report:
    checks: tuple

    @property
    def ok(self) -> bool:
        return all(check.status != "fail" for check in self.checks)

    def lines(self) -> list:
        return [f"{LABELS[c.status]:<6}{c.name:<17}{c.value}" for c in self.checks]


def creates_table(definition: str) -> bool:
    con = sqlite3.connect(":memory:")
    try:
        con.execute(f"CREATE VIRTUAL TABLE probe USING {definition}")
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        con.close()


def fts5_available() -> bool:
    return creates_table("fts5(body)")


def trigram_available() -> bool:
    return creates_table("fts5(body, tokenize = 'trigram')")


def graded(passed: bool, failing_status: str) -> str:
    return "ok" if passed else failing_status


def python_check() -> Check:
    value = f"{platform.python_version()} at {sys.executable}"
    return Check("python", value, graded(sys.version_info >= FLOOR, "fail"))


def sqlite_checks() -> list:
    fts5, trigram = fts5_available(), trigram_available()
    return [
        Check("sqlite", sqlite3.sqlite_version, "ok"),
        Check("fts5", "available" if fts5 else "missing: search cannot work", graded(fts5, "fail")),
        Check("trigram", "available" if trigram else "missing: substring search falls back to LIKE", graded(trigram, "warn")),
    ]


def folder_check(name: str, path: str) -> Check:
    writable = os.path.isdir(path) and os.access(path, os.W_OK)
    return Check(name, path, graded(writable, "fail"))


def storage_checks(storage: Storage, ctx: Context) -> list:
    name = f"storage {storage.name}"
    roots = storage.roots(ctx)
    if not roots:
        setting = getattr(storage.roots, "setting", "")
        return [Check(name, f"no folder configured ({setting})", "warn")]
    return [
        Check(name, f"{root} mounted", "ok") if storage.mounted(root) else Check(name, f"{root} not mounted", "warn")
        for root in roots
    ]


def index_check(kind: Kind, ctx: Context) -> Check:
    path = _db.path_for(kind.name, ctx.data)
    con = _db.connect(path)
    try:
        (count,) = con.execute("SELECT count(*) FROM entities").fetchone()
        return Check("index", f"{count} entities · schema v{_db.schema_version(con)} · {path}", "ok")
    finally:
        con.close()


def kernel_check() -> Check:
    import hoard

    return Check("hoard", hoard.__version__, "ok")


def passed(found: list, name: str) -> bool:
    return any(check.name == name and check.status == "ok" for check in found)


def checks(kind: Kind, ctx: Context) -> Report:
    found = [kernel_check(), python_check(), *sqlite_checks()]
    found += [folder_check("data folder", ctx.data), folder_check("cache folder", ctx.cache)]
    for storage in kind.storages:
        found += storage_checks(storage, ctx)
    if passed(found, "fts5"):
        found.append(index_check(kind, ctx))
    return Report(tuple(found))
