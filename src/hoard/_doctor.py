from __future__ import annotations

import os
import platform
import sqlite3
import sys
from typing import NamedTuple

from hoard import _db, _models
from hoard.contract import Context, Kind, Storage

LABELS = {"ok": "ok", "warn": "warn", "fail": "FAIL"}
FLOOR = (3, 9)


class Check(NamedTuple):
    name: str
    value: str
    status: str


class Report(NamedTuple):
    checks: tuple

    @property
    def ok(self) -> bool:
        return all(check.status != "fail" for check in self.checks)

    def lines(self) -> list:
        return [f"{LABELS[c.status]:<6}{c.name:<16} {c.value}" for c in self.checks]


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
        noun = "entity" if count == 1 else "entities"
        return Check("index", f"{count} {noun} · schema v{_db.schema_version(con)} · {path}", "ok")
    finally:
        con.close()


def kernel_check() -> Check:
    import hoard

    return Check("hoard", hoard.__version__, "ok")


def passed(found: list, name: str) -> bool:
    return any(check.name == name and check.status == "ok" for check in found)


def shown(value: str) -> str:
    return " · ".join(line.strip() for line in value.splitlines() if line.strip())


SECRET_SUFFIX = "_key"


def setting_check(ctx: Context, variable: str, label: str) -> Check:
    value = shown(ctx.setting(variable))
    if value and variable.endswith(SECRET_SUFFIX):
        value = "set"
    return Check("setting", f"{label}: {value}" if value else f"{label}: not set", "ok" if value else "warn")


def server_check(ctx: Context, role: str) -> Check:
    from hoard._http import ModelError

    url = _models.url_of(ctx, role)
    try:
        offered = _models.available(url, _models.key_of(ctx, role))
    except ModelError as error:
        return Check(f"{role} server", f"{url} not reachable: {error.reason}", "warn")
    return Check(f"{role} server", " · ".join([url, *offered]), "ok")


def checks(kind: Kind, ctx: Context, settings=()) -> Report:
    found = [kernel_check(), python_check(), *sqlite_checks()]
    found += [folder_check("data folder", ctx.data), folder_check("cache folder", ctx.cache)]
    found += [setting_check(ctx, variable, label) for variable, label in settings]
    for storage in kind.storages:
        found += storage_checks(storage, ctx)
    found += [server_check(ctx, role) for role in _models.configured(ctx)]
    if passed(found, "fts5"):
        found.append(index_check(kind, ctx))
    return Report(tuple(found))
