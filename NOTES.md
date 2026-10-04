# NOTES

The books-ism list Phase 3 empties, plus where the code departs from the implementation plan
and what still has to be checked on the Mac.

## Where the kernel still assumes a path, a file or a folder

1. `_index.walk` reads folders only. Every `Storage` is a set of folder roots; an API storage
   (Spotify, Phase 4) needs a second walker behind the same `update_storage`.
2. `Sighting.locator` is always a path, and `_system` hands it to macOS `open` / `open -R`;
   a sighting with no locator counts as reachable, which Phase 4 has to revisit.
3. `entities.mtime` is the newest sighting's file mtime; Phase 4 turns it into a kind-supplied sort key.
4. `Kind.icon` returns a bundle-relative path (`icons/epub.png`); covers arrive as bytes on
   `Entity.cover` and are cached as files.
5. `hoard.testing` ships `make_epub` and `make_fb2`, as the plan asks; `make_mp3`/`make_flac` join them in Phase 3.

## Departures from the plan

- **Records are `typing.NamedTuple`, not dataclasses.** Importing `dataclasses` pulls in
  `inspect` and cost 36 ms here, more than starting the interpreter; `test_imports` now bans
  both on the keystroke path. Build and testing code, which never runs on a keystroke, still use dataclasses.
- **`Entity.cover: bytes`.** Readers already have the book open, so they hand the cover over and
  the kernel caches it under `<cache>/icons/<id>.<ext>`. `Kind.icon(entity)` is the fallback.
- **No `Kind.identity`.** The kernel never calls it; Books computes its own fingerprint in its reader.
- **`Context.cache`** joins `data`, `config` and `journal`.
- **Contract helpers** `roots_from(setting)` (one folder per line of a workflow setting) and
  `lazy(module, name)` (keeps readers off the keystroke path; the conformance suite enforces it).
- **FTS rows share `entities.rowid`.** Deleting by the unindexed `id` column made the first
  update of 10 000 files take 17.7 s; by rowid it takes 1.3 s.
- **`hoard.testing` exports lazily** and its fixtures live in `hoard.testing.plugin`, so
  `pytest_plugins = ["hoard.testing"]` still works but importing `hoard.testing.fake` stays light.
- **`hoard.new` is `src/hoard/new.py`** with its files in `src/hoard/template/`.
- **`hoard.build` needs Python ≥ 3.11** for `tomllib`. It is dev-time only and runs through
  `uv run`; the bundle itself still runs on the Command Line Tools' Python 3.9.
- **Pulled forward from Slice B:** `update` already runs through the detached worker with the
  lock-and-rerun progress row, and `open`/`reveal` are kernel verbs.

## Slice B: what hoard hands to kinds

hoard interprets nothing about a kind's places or verbs; it hands over everything it knows and
lets the kind decide.

- **`Found(entity, sightings)`** is what verbs, `default_verb` and `Command.keep` receive.
  Sightings come in the kind's storage order and each says whether it is `reachable` now;
  `found.nearest`, `found.on(storage)` and `found.locator_in(storage)` are conveniences over that.
- **`Context.roots`** carries every storage's roots, so a verb can find where to write without
  knowing how the kind configures its folders.
- **Fold order is the kind's storage order.** A row shows the first reachable copy in that order;
  Books lists `device` before `library`, and another kind can choose the opposite.
- **`Command(label, verb, keep=everything, on=(), off=())`** replaces the plan's
  `Command(label, rows, verb, heads)`. The kernel lists rows and adds the batch row; `on`/`off`
  name storages and are answered in SQL, `keep(found)` is the escape hatch evaluated in Python
  over every match (≈200 ms at 10 000 entities, so prefer `on`/`off`).
- **Batch rows carry the query** (`arg = "batch:loose dune"`), not thousands of ids; `act`
  re-runs the command to expand it.
- **Kernel names:** verbs `open`, `reveal`, `update`, `undo` and commands `update`, `undo`, `rnd`,
  `stats` are reserved; `Kind` refuses to build if a kind reuses them.
- **Journal:** schema v2 adds `journal.kind_of_change`. `act` records one batch per verb run that
  changed something, re-indexes synchronously, and `undo` reverses the newest batch whose verb
  is undoable, skipping batches that cannot be undone.
- **Conformance** now runs every undoable verb over the samples and undoes it, comparing every
  byte, and lists every command through the text renderer.
- **`make doctor`** links the workflow and runs doctor there; doctor fills Alfred's folders from
  `info.plist` and the settings from `prefs.plist`, so no environment variables are needed.

## Slice C: plans

- **`Kind.lint(founds, ctx) -> Plan`**, not the plan's `lint(storage, ctx)`: the kind sees every
  entity with every sighting, plus every storage's roots in `ctx` for files that are not entities
  (junk). It returns steps; it never touches a file itself.
- **Two step verbs, both carried out by the kernel:** `move` (within one storage) and `trash` (into
  `.hoard-trash/` at that storage's root, keeping the relative path and never overwriting).
  Steps may move folders, so a book's KOReader `.sdr` sidecar can travel with it. A step whose
  source is gone, whose target exists, or whose paths lie outside every storage is skipped and counted.
- **`fix [words]`** lists the plan under an "Apply N" row; one row applies one step, the head row
  re-computes and applies the whole plan (`arg = "plan:<words>"`). Words narrow the plan to matching
  entities and drop steps that belong to no entity. The plan's separate `remove` command is not needed:
  duplicates and junk are `trash` steps in the same plan.
- **One journal batch per apply**, undone in reverse; folders emptied by a step are removed and
  recreated on undo. `python3 -m hoard <kind> plan [words]` prints the plan without applying it.
- **`sightings` is keyed `(storage, locator)`** (schema v3), so identical copies in one storage are
  separate sightings: the kind can see duplicates, and they are no longer re-read on every update.
- **Cost:** `fix` lints every entity, about 190 ms at 10 000; it is a deliberate command, not typing.
- **Conformance** applies a kind's whole sample plan and undoes it to the byte, and reads samples
  with the index's own walk, so hidden files such as `._book.epub` are skipped the same way.
- **macOS:** names are compared after NFC normalisation, and a case-only rename is not a conflict.

## To verify on the Mac

- **Keystroke budget in Alfred's debugger.** Measured here on Python 3.9 (stand-in for
  `/usr/bin/python3`): bare interpreter 17 ms, a full `bk amber` from the installed bundle
  over 1 002 books 45 ms. In-process, the worst query over 10 000 entities (a prefix matching
  every row) is 10 ms warm. Levers left if the Mac is slower: drop `typing` for
  `collections.namedtuple` (~5 ms), cache `.pyc` via `PYTHONPYCACHEPREFIX` in the cache folder.
- **`filepicker` `filtermode`.** The build maps `type = "folder"` to `filtermode = 1`, believed
  to mean folders; not confirmed. Books uses `type = "lines"` (a textarea) for its library roots.
- **Script filter, action and notification objects** in `info.plist` are written from the
  Alfred 5 format; import the bundle once and check the canvas wires filter → action → notification.
- **Alfred keeps user configuration in the workflow's `prefs.plist`.** `make doctor` relies on it;
  if your storage lines say "no folder configured", the file lives elsewhere and doctor needs the path.
- **⇧↩ and ⌥↩ modifiers** come from the script filter's `mods`; check they open and reveal.
- **`act open` on a missing `open` command** raises; fine on macOS, worth a friendly line if it ever matters.

## Slice A status

| Item | State |
| --- | --- |
| Alfred timing workflow | replaced by `hoard.build --check` and the timings above; Alfred numbers pending |
| `items`, `render/text`, `api.filter` with the empty row | done |
| `hoard.testing`: FakeKind, conformance plugin | done |
| `hoard.build` bundle, `--check`, `--link`; `hoard.new` | done |
| `test_imports.py` | done, plus `dataclasses`/`inspect` banned |
| `hoard-books` generated, conformance on empty KIND, `make check` | done |
| entity, storage, db v1, index diff on (locator, mtime, size) | done |
| search: prefix words, diacritics, newest first, 40 rows | done |
| Books readers: epub, fb2, fingerprint, covers, format icons | done |

## Slice B status

| Item | State |
| --- | --- |
| fold: one row per id, first reachable storage in kind order, places in the subtitle | done |
| mounted state per storage: "Not reachable", "No folder set" rows on an empty index | done |
| ⇧↩ open, ⌥↩ reveal; ⌘Y, ⌘C, ⌘L via quicklook and text | done |
| `rnd`, `stats`, `update` through the worker | done |
| journal: batches, `undo` row and verb, undoable honoured | done |
| kind verbs and commands with batch rows | done, over `Found` and `on`/`off` |
| Books: device storage and one undoable verb, `copy_in` | done; the rest of the reading loop is the kind's business, not hoard's |

## Slice C status

| Item | State |
| --- | --- |
| `Plan` of `Step(verb, id, before, after, reason)`, one row per step, Apply N, dry run from the CLI | done |
| Books lint: canonical names, byte-identical duplicates, junk; trash inside the storage root | done, device only |
| messy tree cleaned by `fix` and undone to the byte | done, in Books' tests and in the conformance suite |
