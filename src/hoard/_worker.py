from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from typing import Iterator, Optional

from hoard.contract import Context

LOCK = "update.lock"
LOG = "worker.log"


class Busy(Exception):
    pass


def lock_path(ctx: Context) -> str:
    return os.path.join(ctx.cache, LOCK)


def log_path(ctx: Context) -> str:
    return os.path.join(ctx.cache, LOG)


def read_pid(path: str) -> Optional[int]:
    try:
        with open(path) as handle:
            return int(handle.read().strip())
    except (OSError, ValueError):
        return None


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def remove_quietly(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def running(ctx: Context) -> bool:
    path = lock_path(ctx)
    if not os.path.exists(path):
        return False
    pid = read_pid(path)
    if pid is not None and alive(pid):
        return True
    remove_quietly(path)
    return False


@contextmanager
def holding_lock(ctx: Context) -> Iterator[None]:
    running(ctx)
    try:
        descriptor = os.open(lock_path(ctx), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise Busy(lock_path(ctx)) from None
    with os.fdopen(descriptor, "w") as handle:
        handle.write(str(os.getpid()))
    try:
        yield
    finally:
        remove_quietly(lock_path(ctx))


def library_folder() -> str:
    import hoard

    return os.path.dirname(os.path.dirname(os.path.abspath(hoard.__file__)))


def worker_environment() -> dict:
    environ = dict(os.environ)
    paths = [library_folder(), os.getcwd(), environ.get("PYTHONPATH", "")]
    environ["PYTHONPATH"] = os.pathsep.join(path for path in paths if path)
    return environ


def worker_command(module: str, job: str) -> list:
    return [sys.executable, "-m", "hoard", module, "worker", job]


def spawn(module: str, job: str, ctx: Context) -> bool:
    if running(ctx):
        return False
    import subprocess

    with open(log_path(ctx), "a") as log:
        subprocess.Popen(
            worker_command(module, job),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            env=worker_environment(),
            start_new_session=True,
        )
    return True
