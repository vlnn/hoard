from __future__ import annotations

import sqlite3
from typing import NamedTuple, Union

from hoard import _db

JOB = "job"
DONE = "job_done"
TOTAL = "job_total"
EVERY = 25


class Progress(NamedTuple):
    job: str
    done: str
    total: str


def commit_meta(con: sqlite3.Connection, **values: object) -> None:
    for key, value in values.items():
        _db.set_meta(con, key, str(value))
    con.commit()


def begin(con: sqlite3.Connection, job: str, total: Union[int, str] = "") -> None:
    commit_meta(con, **{JOB: job, DONE: 0, TOTAL: total})


def count(con: sqlite3.Connection, total: int) -> None:
    commit_meta(con, **{TOTAL: total})


def advance(con: sqlite3.Connection, done: int) -> None:
    commit_meta(con, **{DONE: done})


def tick(con: sqlite3.Connection, done: int) -> None:
    if done % EVERY == 0:
        advance(con, done)


def current(con: sqlite3.Connection) -> Progress:
    return Progress(
        _db.meta(con, JOB) or "update",
        _db.meta(con, DONE) or "0",
        _db.meta(con, TOTAL) or "",
    )
