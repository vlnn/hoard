# NOTES

The books-ism list Phase 3 empties, plus where the code departs from the implementation plan
and what still has to be checked on the Mac.

## Where the kernel still assumes a path, a file or a folder

1. `_index.walk` reads folders only. Every `Storage` is a set of folder roots; an API storage
   (Spotify, Phase 4) needs a second walker behind the same `update_storage`.
2. `Sighting.locator` is always a path, and `_system` hands it to macOS `open` / `open -R`.
3. `entities.mtime` is the newest sighting's file mtime; Phase 4 turns it into a kind-supplied sort key.
4. `Kind.icon` returns a bundle-relative path (`icons/epub.png`); covers arrive as bytes on
   `Entity.cover` and are cached as files.
5. `sightings` is keyed `(id, storage)`, so two byte-identical files in one storage keep one
   sighting and the other is re-read on every update until `lint` removes duplicates (Slice C).
6. The row's locator is the newest sighting, not the first storage in the kind's order (Slice B fold).
7. `hoard.testing` ships `make_epub` and `make_fb2`, as the plan asks; `make_mp3`/`make_flac` join them in Phase 3.

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
