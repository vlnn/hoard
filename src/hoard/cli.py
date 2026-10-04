from __future__ import annotations

import sys

USAGE = """usage: python3 -m hoard <kind module> <mode>
  filter [--text] [query]   rows for what was typed, as Alfred JSON or plain text
  act <verb> [ids…]         run a verb and print the notification line
  update [--full]           read every storage now
  worker update             the detached background update
  plan [words]              print the fix plan without applying it
  ask [name|tag] [--dry-run]  ask the chat model now, or print what would be asked
  doctor                    check python, sqlite, folders and storages"""


def load_kind(module: str):
    import importlib

    return importlib.import_module(module).KIND


def filter_mode(module: str, args: list) -> None:
    from hoard import api

    as_text = args[:1] == ["--text"]
    typed = " ".join(args[1:] if as_text else args)
    items = api.filter(load_kind(module), typed)
    if as_text:
        from hoard.render import text

        print("\n".join(text.render(items)))
    else:
        from hoard.render import alfred

        print(alfred.render(items))


BACKGROUND = {"update": "Updating the index", "ask": "Asking the model"}


def start_job(module: str, job: str) -> str:
    from hoard import _worker, api

    ctx = api.context(load_kind(module))
    return BACKGROUND[job] if _worker.spawn(module, job, ctx) else "Already working"


def act_mode(module: str, args: list) -> None:
    from hoard import api

    verb, ids = (args[0], args[1:]) if args else ("", [])
    print(start_job(module, verb) if verb in BACKGROUND else api.act(load_kind(module), verb, ids))


def update_mode(module: str, args: list) -> None:
    from hoard import api

    print(f"{api.update(load_kind(module), full='--full' in args)} found")


TRUE = {"1", "true", "yes", "on"}


def ask_quietly(kind, ctx) -> None:
    from hoard import api

    try:
        print(f"{api.ask(kind, ctx)} answered", flush=True)
    except api.ModelError as error:
        print(f"ask stopped: {error}", file=sys.stderr, flush=True)


def run_job(kind, ctx, job: str) -> None:
    from hoard import api

    if job == "update":
        print(f"{api.update(kind, ctx)} found", flush=True)
    if job == "ask" or ctx.setting("hoard_ask_on_update").strip().lower() in TRUE:
        ask_quietly(kind, ctx)


def worker_mode(module: str, args: list) -> None:
    from hoard import _worker, api

    if args not in (["update"], ["ask"]):
        usage()
    kind = load_kind(module)
    ctx = api.context(kind)
    try:
        with _worker.holding_lock(ctx):
            run_job(kind, ctx, args[0])
    except _worker.Busy:
        print("another worker holds the lock", file=sys.stderr)


def ask_mode(module: str, args: list) -> None:
    from hoard import api

    questions = [word for word in args if word in ("name", "tag")] or None
    kind = load_kind(module)
    if "--dry-run" in args:
        print("\n".join(api.ask_dry_run(kind, questions=questions)))
        return
    print(f"{api.ask(kind, questions=questions)} answered")


def doctor_mode(module: str, args: list) -> None:
    import os

    from hoard import _alfred, api

    _alfred.fill_from_workflow(os.getcwd(), os.environ)
    report = api.doctor(load_kind(module), settings=_alfred.declared_settings(os.getcwd()))
    print("\n".join(report.lines()))
    sys.exit(0 if report.ok else 1)


def plan_mode(module: str, args: list) -> None:
    from hoard import _plan, api

    for step in api.plan(load_kind(module), " ".join(args)):
        print(_plan.describe(step))


MODES = {
    "plan": plan_mode,
    "ask": ask_mode,
    "filter": filter_mode,
    "act": act_mode,
    "update": update_mode,
    "worker": worker_mode,
    "doctor": doctor_mode,
}


def usage() -> None:
    print(USAGE, file=sys.stderr)
    sys.exit(2)


def main(module=None, argv=None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if module is None:
        module, argv = (argv[0], argv[1:]) if argv else (None, [])
    mode = MODES.get(argv[0]) if argv else None
    if module is None or mode is None:
        usage()
    mode(module, argv[1:])
