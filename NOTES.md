# NOTES

Three things the implementation plan asks this file to hold: every place the kernel still
assumes files and folders, where the code departs from the plan, and what can only be checked on
the Mac. Phases 3–5 of the plan (music files, Spotify, a second API kind) were replaced by one
Phase 3, Pictures; see the end of this file.

## Where the kernel still assumes a path, a file or a folder

The kernel's own files (database, cache, lock, log, icons) are not on this list; storages are.

1. **Storages are folders.** `_index.walk` lists files under each root and calls the reader with a
   path; `Storage.mounted` defaults to `os.path.isdir`; `roots_from` reads one folder per line.
   An API storage needs a second walker behind `update_storage`; none is planned for 1.0.
2. **Change detection is `(locator, mtime, size)`** from `os.stat`; an API storage needs its own cursor.
3. **Newest first is file mtime.** `entities.mtime` is the newest sighting's mtime; an API kind
   would need a kind-supplied sort key.
4. **Reachability is "under a mounted root"** (`_fold`); a sighting without a locator counts as
   reachable, which an API kind would revisit with the last worker run's result.
5. **`open` and `reveal` hand the locator to macOS `open`** (`_system`).
6. **Plan steps are file-system moves** (`_plan`): `move` within a root, `trash` into
   `<root>/.hoard-trash/`. A kind whose storage is not a folder has no steps to offer yet.
7. **Covers arrive as bytes and are cached as files**; `Kind.icon` returns a path, bundle-relative
   or absolute (Pictures returns the picture itself).
8. **Derived producers receive a `Found`** and, so far, every producer reads `found.nearest.locator`.
9. **`hoard.testing` ships `make_epub` and `make_fb2`**, as the plan asks. Picture builders
   (`make_jpeg`, `make_png`, `make_svg`, an EXIF/TIFF encoder) live in hoard-pictures' own tests:
   they serve one kind, so the library does not carry them.

## Departures from the plan

**Contract**
- Records are `typing.NamedTuple`, not dataclasses: importing `dataclasses` pulls in `inspect` and
  cost more than starting the interpreter. `test_imports` bans both on the keystroke path.
- Kinds receive `Found(entity, sightings)`: verbs, `default_verb`, `Command.keep`, `lint` and
  derived producers all get it. Sightings come in the kind's storage order and say whether they are
  reachable; `nearest`, `on()` and `locator_in()` are conveniences over that.
- `Context` carries `cache` and `roots` (every storage's folders) besides `data`, `config` and
  `journal`, so verbs find where to write without knowing how the kind is configured.
- `Entity.cover: bytes`; the kernel caches it and `Kind.icon(entity)` is only the fallback.
- No `Kind.identity`: the kernel never calls it; readers fingerprint on their own.
- `Command(label, verb, keep=everything, on=(), off=())` replaces `Command(label, rows, verb, heads)`.
  The kernel lists rows and adds the batch row; `on`/`off` are answered in SQL, `keep` in Python over
  every match (about 200 ms at 10 000 entities).
- `Kind.lint(founds, ctx) -> Plan`, not `lint(storage, ctx)`: the kind proposes `move` and `trash`
  steps and the kernel carries them out. There is no separate `remove` command; duplicates and junk
  are steps in the same `fix` plan.
- `Kind.derive = {key: producer(found)}` is the hook that fills `derived`; values are searchable.
- `Kind.labels` holds `one` and `many`, the nouns the kernel counts in.
- Reserved names: verbs `open`, `reveal`, `update`, `undo`, `apply`; commands `update`, `undo`,
  `rnd`, `stats`, `fix`. `Kind` refuses to build if a kind reuses them.
- Helpers `roots_from(setting)` and `lazy(module, name)` live in the contract.

**Kernel**
- Fold order is the kind's storage order; a row shows the first reachable copy.
- Batch rows carry a query, not ids: `batch:<command words>` and `plan:<words>`; `act` re-runs it.
- FTS rows share `entities.rowid`: deleting by the unindexed `id` made a 10 000-file update take 17.7 s.
- Schema v2 adds `journal.kind_of_change`; v3 keys `sightings` by `(storage, locator)` so identical
  copies in one storage are visible and not re-read.
- `update` runs through the detached worker from Slice A on.

**Tooling**
- `hoard.testing` exports lazily and its fixtures live in `hoard.testing.plugin`, so importing
  `hoard.testing.fake` stays off pytest; `pytest_plugins = ["hoard.testing"]` still works.
- `hoard.new` is `src/hoard/new.py` with its files in `src/hoard/template/`; it can pin hoard by path
  (`--hoard`) or by tag (`--hoard-git URL --hoard-tag v0.1.0`).
- `hoard.build` needs Python ≥ 3.11 for `tomllib`; it is dev-time only, the bundle still runs on 3.9.
- `make doctor` runs doctor inside the linked workflow, which reads Alfred's folders from `info.plist`
  and the settings from `prefs.plist`; `make ci` builds and checks a clean clone.

## Phase 2 departures

- **Model settings belong to hoard.** Every build appends `hoard_chat_url`, `hoard_embeddings_url`
  and `hoard_ask_on_update` to the kind's configuration; doctor checks each server answers.
- **Pickers reopen Alfred with `osascript`** (`tell application id "com.runningwithcrayons.Alfred" to
  search …`) instead of an external trigger: ↩ on a tag row and ⌘↩ reopen at `tag #<id>`, ⌃↩ at
  `like #<id>`.
- **Evidence is computed once, at index time** (schema v4 adds `entities.evidence` and its hash;
  the migration makes every file look changed so the next update fills it).
- **The ask job asks and embeds**; it runs on ↩ over an "Ask N" or "Embed N new" row, or after an
  update when `hoard_ask_on_update` is on. A dead server stops the job and leaves what was stored.
- **Name overlays** are re-applied after every re-read from the stored answer, so they need no table
  of their own; accepting and undoing go through the journal like any other batch.
- **Reserved:** commands `model`, `name`, `tag`, `like`; verbs `use_model`, `ask`, `accept`, `pick`,
  `set_tag`, `accept_tags`, `like`, `embed`. `model`, `name` and `like` are ordinary search words
  until their server is set, and `tag` until the kind has tags.
- **Neighbours are ranked when asked** (since 1.0, schema v5). Ranking on store was quadratic:
  17.7 s for 1 000 local vectors. Each vector now carries a 128-bit signature from sparse random
  planes, read through a covering index; `like` shortlists the 200 closest signatures and scores
  those exactly, about 15 ms among 10 000 × 1 024 here. Vectors stored before v5 are made again.

## To verify on the Mac

- **Keystroke budget in Alfred's debugger** (the Phase 0 gate). Here, on Python 3.9: bare
  interpreter 17 ms, a full `bk amber` from the bundle over 1 002 books 45 ms; in-process, the worst
  search over 10 000 entities is about 10 ms warm, `fix` about 190 ms.
- **`prefs.plist` holds Alfred's user configuration.** If `make doctor` reports settings as
  "not set" although Alfred has them, the file lives elsewhere.
- **`filtermode = 1` means folders** in a `filepicker` setting; unconfirmed. Books uses text areas.
- **The canvas wires filter → action → notification**, and ⇧↩ / ⌥↩ open and reveal.
- **`osascript` may ask once for permission** to control Alfred; the picker and ⌃↩ need it.
- **Pictures in Alfred:** a jpg or png path as the row icon shows the picture; whether Alfred draws
  an svg icon is unconfirmed.
- **Phase 2 exit on a real library:** `like` gives sensible neighbours with your embeddings model,
  tag suggestions are accepted in a batch and undone, and `bk` is as fast as before.

## Phase 1 status

| Slice | Item | State |
| --- | --- | --- |
| A | text renderer, `api.filter`, empty-index row | done |
| A | `hoard.testing` (FakeKind, conformance plugin), `hoard.build`, `hoard.new`, `test_imports` | done |
| A | schema, index diff on `(locator, mtime, size)`, search with folded diacritics | done |
| A | Books readers (epub, fb2), fingerprints, covers | done |
| A | Alfred timing workflow | replaced by `hoard.build --check`; Alfred numbers pending |
| B | fold, reachability, ⇧↩ / ⌥↩, "not reachable" rows, `rnd`, `stats` | done |
| B | journal, `undo`, kind verbs and commands with batch rows | done |
| B | Books: device storage and `copy_in` | done; the rest of the reading loop is the kind's business |
| C | plans: `fix`, Apply N, dry run, undo to the byte | done |
| C | Books lint on the device: names, duplicates, junk, KOReader sidecars | done |
| D | settings declared in `plist.toml`, reported by doctor | done |
| D | `derived` table and its hook, no producer in Books | done |
| D | `docs/writing-a-kind.md` | done |
| D | `hoard 0.1.0` tagged, Books on the tag, CI from a clean clone | tag and `make ci` ready; Books switches once the library has a URL |

## Phase 3: Pictures

The plan's Phases 3–5 were replaced by one kind, `hoard-pictures` (keyword `pi`): every jpg, jpeg,
png and svg under the folders in its "Picture folders" setting, and similar pictures by metadata.

| Item | State |
| --- | --- |
| 3a `LocalVectors(name, vector)`: like without a model server, vectors made by update | done |
| 3a like ranked when asked from vector signatures, update linear | done |
| 3b readers on the standard library: JPEG EXIF (both byte orders, orientation, GPS), PNG `IHDR`, `eXIf`, `tEXt`, `iTXt`, SVG size, `viewBox`, `title`, `desc` | done |
| 3b feature vector: time and place over many wavelengths, camera, lens and folder buckets, shape | done |
| 3b each picture is its own row icon | done; Alfred to confirm |
| 3c `docs/writing-a-kind.md` on `LocalVectors`, this file, `hoard 1.0.0` | done |

Measured here: an update over 3 000 jpegs takes 3.6 s, `like` among them 21 ms. Pictures has no
verbs or plan; the kernel's open and reveal are enough. The folder assumptions above all hold for
it, which is why it could be written without touching the walker.
