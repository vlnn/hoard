# hoard

A small library for Alfred workflows. It has two floors.

The **toolkit**, `hoard.alfred`, is what any workflow needs: rows and their JSON, folding and
word-prefix matching, the settings Alfred passes in, the macOS calls behind open, reveal, trash and
notify, and one client for a model, whether a `llama-server` or Apple Intelligence on the device.
A workflow that keeps its own canvas in `workflow/info.plist` builds on the toolkit alone.

The **kernel** is for workflows over *collections of things*. A *kind* (books, pictures, music
files…) lives in its own repository, declares itself as one `KIND = Kind(...)`, passes the
conformance suite shipped here, and gets an index, search, places, verbs with undo, tags, standard
spellings and *like* from the kernel.

Either way the build vendors this library next to the workflow's own package. Nothing is installed
on the machine that runs the workflow; the bundle runs on the system `/usr/bin/python3` with the
standard library only.

## Public surface

| Module | For |
| --- | --- |
| `hoard.alfred` | `Item`, `Head`, `Mod`, `Items`, `render`; `fold`, `words`, `matches`; `is_on`, `data_folder`, `cache_folder` |
| `hoard.alfred.chat` | `Server`, `request`, `stream`, `respond`, `without_thinking`, `reachable`, `ModelError` |
| `hoard.alfred.apple` | `respond` through the on-device model; `AppleError` is a `ModelError` |
| `hoard.alfred.macos` | `open`, `reveal`, `trash`, `copy`, `notify` |
| `hoard.contract` | `Kind`, `Storage`, `Entity`, `Sighting`, `Found`, `Verb`, `Command`, `Change`, `Plan`, `Step`, `Context`, `TextEmbedding`, `LocalVectors`, `roots_from`, `lines_from`, `lazy` |
| `hoard.api` | `filter(kind, typed)`, `act(kind, verb, ids)`, `update(kind)`, `plan(kind)`, `carry_out(kind, steps, ctx)`, `restore(kind, changes, ctx)`, `ask(kind)`, `embed(kind)`, `doctor(kind)` |
| `hoard.testing` | the conformance suite (`Conformance`), `FakeKind`, `make_epub`, `make_fb2`, fixtures `temp_tree`, `context_with` |
| `hoard.build` | `python3 -m hoard.build [--check \| --link]` from a workflow repository |

`python3 -m hoard.new <kind>` writes a new kind repository; `docs/writing-a-kind.md` walks through
the rest. Everything with a leading underscore is private.

## A workflow on the toolkit alone

`workflow/plist.toml` names the hand-made canvas, where the package lives and what else the canvas
needs in the bundle:

```toml
kind = "wisp"
name = "Wisp"
bundleid = "com.example.wisp"
plist = "workflow/info.plist"
source = "src"
assets = ["workflow/view"]
```

`python3 -m hoard.build` stamps the name, bundle id and version into that plist, copies the package,
the icons and the assets next to a copy of this library, and `--check` imports the package from the
bundle on the system python. The canvas calls the package itself, `/usr/bin/python3 -m wisp …`,
and the package imports `hoard.alfred`. `import hoard.alfred` loads neither SQLite nor the network;
`chat`, `apple` and `macos` are imported by name where they are used.

## Working on it

    uv sync
    uv run pytest                          the kernel against FakeKind
    uv run pytest -m slow                  performance budgets
    uv run --isolated --python 3.9 pytest  the macOS Command Line Tools floor
    uv run python -m hoard <kind module> filter --text "words"
    uv run python -m hoard <kind module> plan                  the fix plan, without applying it

See `NOTES.md` for where the code departs from the plan and what remains to check in Alfred.
