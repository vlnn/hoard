# Writing a kind

A kind is a small Python package in its own repository that tells hoard what a collection is: where
its things live, how to read one, and what the keys do. hoard does the rest: the index, search,
the Alfred rows, the journal and undo, plans, the background update and the bundle. This guide
follows the order in which Books needed things; every example is from `hoard-books`.

A kind imports only the public surface: `hoard.contract`, `hoard.api`, `hoard.testing` and
`hoard.build`. Anything with a leading underscore is private, and the conformance suite fails a kind
that imports it.

## 1. Start a repository

```
python3 -m hoard.new books --keyword bk --title Books --bundle-prefix com.you --into ~/src
cd ~/src/hoard-books && uv sync && make test
```

The template writes a package with an empty `KIND`, a conformance test that already passes, the
workflow description in `workflow/plist.toml`, an icon, and a Makefile:

| Target | Does |
| --- | --- |
| `make test` | the shipped conformance suite plus your own tests |
| `make test-system` | the same on `/usr/bin/python3`, the interpreter the workflow runs on |
| `make check` | builds `dist/<kind>.alfredworkflow` and answers an empty query from it |
| `make link` | installs a workflow whose code is symlinked to your checkout and the library's |
| `make doctor` | runs doctor inside that installed workflow, with Alfred's folders and your settings |
| `make ci` | clones the repository afresh, installs, tests and checks the bundle |

While the library and the kind change together, the kind depends on a hoard checkout by path. Once
hoard is tagged, pin it instead: `--hoard-git <url> --hoard-tag v1.0.0` for a new kind, or edit
`[tool.uv.sources]` in an existing one. `make ci` only passes once the dependency no longer needs a
sibling checkout.

## 2. Declare the kind

A kind is one object built at import time, so a mistake fails at `doctor` or in the tests, never on
a keystroke:

```python
from hoard.contract import Kind, Storage, Verb, lazy, roots_from

from books.entity import FIELDS, default_verb, evidence, format_icon

READ = lazy("books.readers", "read")

KIND = Kind(
    name="books",
    keyword="bk",
    storages=(
        Storage("device", roots_from("device"), READ),
        Storage("library", roots_from("library"), READ),
    ),
    fields=FIELDS,
    evidence=evidence,
    icon=format_icon,
    default_verb=default_verb,
    verbs={"copy_in": Verb("Copy to the device", lazy("books.verbs", "copy_in"), lazy("books.verbs", "remove_copies"))},
    lint=lazy("books.lint", "lint"),
    labels={"one": "book", "many": "books"},
)
```

Only `name`, `keyword`, `storages`, `fields` and `evidence` are required. With just those, a kind
already has search, newest-first listing, ⇧↩ open, ⌥↩ reveal, `update`, `rnd` and `stats`.

**Keep the module light.** Alfred starts a fresh Python on every keystroke, and the kind's
`__init__` is imported each time. Anything that pulls in `zipfile`, `xml`, `urllib`, `shutil` or
other heavy modules goes behind `lazy(module, name)`, which imports on first call. The conformance
suite imports your package in a clean interpreter and fails if a slow module is loaded.

## 3. Read things into entities

A storage's `reader(path)` returns an `Entity`, or `None` for files that are not yours:

```python
Entity(id, title, fields=(authors, series, year, fmt, path), text=excerpt, cover=jpeg_bytes)
```

- **`id`** is the identity hoard folds by. Books uses a content fingerprint (blake2b over the bytes),
  so the same book in two places, or twice in one place, is one entity with several sightings.
- **`fields`** is one string per label in `KIND.fields`, in order; empty strings are fine. They make
  the row's subtitle and are searchable.
- **`text`** is an excerpt for `evidence` (Books keeps the first 2 000 characters).
- **`cover`** is image bytes, or `b""`. hoard caches it by id; without a cover, `Kind.icon(entity)`
  may return a path relative to the bundle, such as `icons/epub.png` from `workflow/icons/`.

A reader should never raise on a bad file. Books falls back to the file name as the title, so a
broken book is still found and can be fixed by hand. If a reader does raise, hoard skips the file,
logs it to `worker.log`, and tries again on the next update.

## 4. Storages and settings

`roots_from("device")` reads the workflow setting `device`, one folder per line. Declare each setting
in `workflow/plist.toml`; the build turns it into Alfred's configuration screen:

```toml
[[configuration]]
variable = "device"
label = "E-reader folder"
type = "lines"
description = "Where the e-reader is mounted, e.g. /Volumes/KOBOeReader"
```

`type` is one of `lines` (a text area), `text`, `folder` (a picker) or `checkbox`. `make doctor`
lists every declared setting and says which are empty.

**Order matters.** When an entity is in several storages its row shows the first reachable copy in
the order of `storages`, and the subtitle names the others: `device +library`. A storage whose root
is not mounted keeps its entities in the index; their rows fall back to the next reachable copy.

## 5. What ↩ does: `default_verb` and verbs

Everything hoard hands a kind about an entity arrives as a `Found`: the entity plus every
`Sighting(storage, locator, mtime, size, reachable)`, in storage order. `found.tags` holds its tags,
sorted, set by hand or accepted from the model, so verbs and `lint` can act on them.

```python
def default_verb(found: Found) -> str:
    return "open" if found.on("device") else "copy_in"
```

A verb is `Verb(label, run, undo)`. `run(founds, ctx)` does the work and returns one
`Change(id, kind_of_change, before, after)` per thing it changed, with plain JSON-able values.
`undo(changes, ctx)` receives the same records back. `ctx.roots_of("device")` gives that storage's
folders.

```python
def copy_in(founds, ctx):
    roots = ctx.roots_of("device")
    if not roots:
        return []
    changes = []
    for found in founds:
        paths = copy_target(found, roots[0])
        if paths:
            shutil.copyfile(*paths)
            changes.append(Change(found.entity.id, "copy", *paths))
    return changes


def remove_copies(changes, ctx):
    for change in changes:
        os.remove(change.after)
```

hoard writes the changes to the journal as one batch, re-indexes, and shows `Copy to the device: Dune`
as the notification. `bk undo` reverses the newest batch. A verb with `undo=None` is marked
*cannot be undone* and is skipped by undo. A verb that returns no changes records nothing.

## 6. Commands

A command is a first word that lists a subset with its own ↩:

```python
Command("Copy", "copy_in", off=("device",))
```

`on` and `off` name storages and are answered in SQL, so they stay fast on large collections. For
anything else, `keep(found) -> bool` sees every row in Python; it works, but it costs about 200 ms
at 10 000 entities. The rows come under a "Copy all N" row that runs the verb on all of them.

`update`, `undo`, `rnd`, `stats` and `fix` belong to hoard.

Two or more letters of a command, with nothing after them, put a row per matching command first
(`bk up` → *bk update*); ↩ or ⇥ on it completes the word, and the search for the letters follows.

## 7. Plans: `fix`

`lint(founds, ctx)` returns a `Plan` of `Step(verb, id, before, after, reason)`. A kind proposes; hoard
carries out. There are two step verbs:

- `move`: rename or move a file or folder within one storage root;
- `trash`: move it into `.hoard-trash/` at that root, keeping its relative path.

Books proposes canonical names on the device, moves a book's KOReader `.sdr` folder with it, and
trashes byte-identical duplicates and junk such as `._*` files. `bk fix` lists the steps under
"Apply N"; `python3 -m hoard books plan` prints them without touching anything. A step whose target
exists or whose paths are outside every storage is skipped and counted. An apply is one journal
batch, and `undo` restores every byte and folder.

Compare file names after `unicodedata.normalize("NFC", …)`: macOS lists names decomposed, and a
name that differs only in that form would otherwise be renamed on every run.

## 8. Derived values

`derive={"text": producer}` asks hoard to call `producer(found, ctx)` once per entity and store the
returned text, which becomes searchable. Update only asks for what is missing, a full rebuild keeps
what was made, and a producer that raises is asked again next time. Put slow producers behind
`lazy`; they run in the background worker.

Update makes a kind's `LocalVectors` first and derived values after, so one analysis can serve
both: Pictures asks Vision once per picture for the feature print, labels and text while making
the vector, and its `labels` and `text` producers pick up what that pass kept.

## 9. Models: `name`, `tag` and `like`

Everything here stays invisible until a model server is set in the workflow configuration.
The build adds only the server settings a kind has work for: `hoard_chat_url` and its key when the
kind is `nameable` or has `tags`, `hoard_embeddings_url` and its key when `like` is
`TextEmbedding()`, and `hoard_ask_on_update` with either. A kind with none of these, such as
Pictures, is never asked for a server. `bk model` lists what each llama-server offers and ↩ picks one.
Models are only ever called from the background worker, never on a keystroke.

```python
KIND = Kind(
    ...,
    nameable=("authors", "series", "year"),
    tags=lines_from("tags"),
)
```

- **`nameable`** lists the fields the chat model may correct. Its answer comes with a confidence; a
  confident answer overlays the title and those fields in the index, never the file, and survives
  re-reads, so `fix` already names files from the corrected metadata. Unsure answers wait in
  `bk name` under "Accept N".
- **`tags(ctx)`** returns the allowed tags (Books reads them from a setting). `bk tag` lists untagged
  rows with the model's guess as `scifi?`; ↩ or ⌘↩ opens a picker; "Accept N suggested" applies the
  guesses in one batch. A hand tag always wins and drops the model's guess. Tags are searchable.
- **`like`** defaults to `TextEmbedding()`: the embeddings model reads your `evidence`, trimmed to
  1 500 characters. `bk like <words>`, `bk like #<id>` or ⌃↩ on any row lists the nearest entities with
  a percentage. With no words, `like` starts from `last_opened(ctx)` if the kind supplies it, else from
  the newest entity. Set `like=None` to turn it off.

### Like without a model server: `LocalVectors`

When the kind can compute similarity itself, hand hoard the numbers:

```python
KIND = Kind(
    ...,
    like=LocalVectors(f"vision-darwin{DARWIN}", lazy("pictures.vision", "vector")),
)
```

`vector(found, ctx)` returns a sequence of floats, the same length for every entity. Update calls
it once per entity that has no vector yet, in the background, and stores it scaled to unit
length, so `like` works with no server set and never offers to embed. If it raises, that entity
is left out and the error goes to the worker log. `ctx` is there for whatever the kind needs:
`ctx.cache` for something built once, `ctx.setting(...)` for its own settings.

The name says what the numbers mean. Change it when that changes and the old vectors are ignored;
the next update makes new ones. Hoard Pictures puts the macOS major release in the name, because a
new macOS may bring a new Vision feature print that cannot be compared with the old one.

Hoard Pictures is the worked example: a small Swift program, shipped as source and compiled into
`ctx.cache` with the Command Line Tools on first use, stays running for the whole update and
answers one picture path per line with Apple Vision's image feature print. Nothing leaves the Mac.

`like` shortlists by a 128-bit signature of each vector and scores the shortlist exactly, so it
stays a keystroke over tens of thousands of entities, whether vectors have a few hundred numbers
or two thousand.

`evidence(entity)` is what every model sees, so make it the title and fields a person would use to
recognise the thing, plus a short excerpt. `python3 -m hoard books ask name --dry-run` prints exactly
what would be sent.

## 10. Tests

`tests/test_conformance.py` is three lines from the template; give it samples:

```python
class TestConformance(Conformance):
    kind = KIND

    def make_samples(self, storage, root):
        if storage == "device":
            make_epub(root / "ubik.epub", title="Ubik", authors=("Philip K. Dick",), date="1969")
            (root / "._ubik.epub").write_bytes(b"\x00\x05\x16\x07")
            return
        make_epub(root / "Dune.epub", title="Dune", authors=("Frank Herbert",), date="1965")
        (root / "Broken.epub").write_bytes(b"PK not a zip")
```

The suite then checks, over your samples, that every entity has one string per field, evidence is
text, rows render, every command lists, every undoable verb undoes to the byte, the whole plan
applies and undoes to the byte, and that the package imports nothing private and nothing slow.

`hoard.testing` also gives the fixtures `temp_tree` and `context_with`, and builders such as
`make_epub` and `make_fb2` that write real files in a test, so no binary fixtures are checked in.
For your own tests, drive the kind through `hoard.api` and the text renderer:

```python
ctx = make_context(tmp_path / "workflow", library=str(library), device=str(device))
api.update(KIND, ctx)
assert text.render(api.filter(KIND, "dune", ctx)) == ["Dune | library · Frank Herbert · 1965 · epub · …"]
```

Write tests that hold on macOS as well as Linux: file names are compared without case there, and
listed in decomposed Unicode.
