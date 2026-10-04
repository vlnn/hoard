# hoard

A small library for Alfred workflows over collections of things. A *kind* (books, music files,
a Spotify library…) lives in its own repository, declares itself as one `KIND = Kind(...)`,
passes the conformance suite shipped here, and builds a `.alfredworkflow` that vendors this
library next to it. Nothing is installed on the machine that runs the workflow; the bundle runs
on the system `/usr/bin/python3` with the standard library only.

## Public surface

| Module | For |
| --- | --- |
| `hoard.contract` | `Kind`, `Storage`, `Entity`, `Verb`, `Command`, `Change`, `Plan`, `Step`, `Context`, `roots_from`, `lazy` |
| `hoard.api` | `filter(kind, typed)`, `act(kind, verb, ids)`, `update(kind)`, `doctor(kind)` |
| `hoard.testing` | the conformance suite (`Conformance`), `FakeKind`, `make_epub`, `make_fb2`, fixtures `temp_tree`, `context_with` |
| `hoard.build` | `python3 -m hoard.build [--check \| --link]` from a kind repository |

`python3 -m hoard.new <kind>` writes a new kind repository. Everything with a leading underscore is private.

## Working on it

    uv sync
    uv run pytest                          the kernel against FakeKind
    uv run pytest -m slow                  performance budgets
    uv run --isolated --python 3.9 pytest  the macOS Command Line Tools floor
    uv run python -m hoard <kind module> filter --text "words"

See `NOTES.md` for where the code departs from the plan and what remains to check in Alfred.
