from __future__ import annotations

import json
import sqlite3
import sys
import time
from collections import Counter
from typing import Iterator, NamedTuple, Optional

from hoard import _journal
from hoard._text import refresh_text
from hoard.contract import TAGS, Change, Context, Kind, Spelling, Standard

APART = "apart"
RULE = "rule"
HAND = "hand"
VERB = "standardize"
EVERY = "std:"
ONE = "std#"
CHOICE = "stdpick:"

MAPPED = "SELECT subject, variant, standard FROM standards WHERE set_by != ?"
PROPOSALS = "SELECT n, subject, standard, variants_json, shown_json, count FROM proposals"


class Pending(NamedTuple):
    n: Optional[int]
    subject: str
    standard: str
    variants: tuple
    shown: tuple
    count: int
    trivial: bool = False

    def rechosen(self, standard: str) -> Pending:
        spellings = (self.standard, *self.shown)
        others = tuple(spelling for spelling in (self.standard, *self.variants) if spelling != standard)
        shown = tuple(spelling for spelling in spellings if spelling != standard)
        return self._replace(standard=standard, variants=others, shown=shown)


def mapping(con: sqlite3.Connection) -> dict:
    table = {}
    for subject, variant, standard in con.execute(MAPPED, (APART,)):
        table.setdefault(subject, {})[variant] = standard
    return table


def with_standards(con: sqlite3.Connection, ctx: Context) -> Context:
    return ctx._replace(standards=mapping(con))


def standard_of(con: sqlite3.Connection, subject: str, value: str) -> str:
    row = con.execute(
        "SELECT standard FROM standards WHERE subject = ? AND variant = ? AND set_by != ?", (subject, value, APART)
    ).fetchone()
    return row[0] if row else value


def settled(con: sqlite3.Connection, subject: str) -> set:
    return {variant for (variant,) in con.execute("SELECT variant FROM standards WHERE subject = ?", (subject,))}


def values_of(text: str, separator: str) -> list:
    if not separator:
        return [text] if text else []
    return [part.strip() for part in text.split(separator) if part.strip()]


def standardized(text: str, table: dict, separator: str) -> str:
    values = values_of(text, separator)
    if not any(value in table for value in values):
        return text
    mapped = dict.fromkeys(table.get(value, value) for value in values)
    return separator.join(mapped) if separator else next(iter(mapped))


def field_subjects(kind: Kind) -> list:
    return [(subject, kind.fields.index(subject), record.separator) for subject, record in kind.standards.items() if subject != TAGS]


def standardized_fields(kind: Kind, fields: tuple, table: dict) -> tuple:
    named = list(fields)
    for subject, position, separator in field_subjects(kind):
        named[position] = standardized(named[position], table.get(subject, {}), separator)
    return tuple(named)


def fields_of(con: sqlite3.Connection, entity_id: str) -> Optional[tuple]:
    row = con.execute("SELECT fields_json FROM entities WHERE id = ?", (entity_id,)).fetchone()
    return tuple(json.loads(row[0])) if row else None


def write_fields(con: sqlite3.Connection, entity_id: str, fields) -> None:
    con.execute("UPDATE entities SET fields_json = ? WHERE id = ?", (json.dumps(list(fields), ensure_ascii=False), entity_id))


def overlay(con: sqlite3.Connection, kind: Kind, entity_id: str) -> None:
    fields = fields_of(con, entity_id) if field_subjects(kind) else None
    if fields is None:
        return
    named = standardized_fields(kind, fields, mapping(con))
    if named != fields:
        write_fields(con, entity_id, named)


def field_spellings(con: sqlite3.Connection, kind: Kind, subject: str) -> Counter:
    position, separator = kind.fields.index(subject), kind.standards[subject].separator
    counts = Counter()
    for (fields_json,) in con.execute("SELECT fields_json FROM entities"):
        counts.update(set(values_of(json.loads(fields_json)[position], separator)))
    return counts


def tag_spellings(con: sqlite3.Connection, kind: Kind, ctx: Context) -> Counter:
    counts = Counter(dict(con.execute("SELECT tag, count(DISTINCT id) FROM tags GROUP BY tag")))
    for tag in kind.tags(ctx):
        counts.setdefault(tag, 0)
    return counts


def spellings_of(con: sqlite3.Connection, kind: Kind, ctx: Context, subject: str) -> Counter:
    return tag_spellings(con, kind, ctx) if subject == TAGS else field_spellings(con, kind, subject)


def asked(kind: Kind, ctx: Context, subject: str, counts: Counter) -> list:
    spellings = [Spelling(value, count) for value, count in sorted(counts.items())]
    try:
        return list(kind.standards[subject].propose(spellings, ctx))
    except Exception as error:
        print(f"standards {subject}: {error!r}", file=sys.stderr)
        return []


def pending(subject: str, standard: Standard, counts: Counter, unavailable: set) -> Optional[Pending]:
    variants = tuple(v for v in dict.fromkeys(standard.variants) if v != standard.standard and v not in unavailable)
    shown = tuple(v for v in variants if v in counts)
    if not shown:
        return None
    return Pending(None, subject, standard.standard, variants, shown, sum(counts[v] for v in shown), standard.trivial)


def proposed_for(con: sqlite3.Connection, kind: Kind, ctx: Context, subject: str) -> Iterator[Pending]:
    counts = spellings_of(con, kind, ctx, subject)
    unavailable, mapped = settled(con, subject), ctx.standards.get(subject, {})
    for standard in asked(kind, ctx, subject, counts):
        found = None if standard.standard in mapped else pending(subject, standard, counts, unavailable)
        if found is not None:
            unavailable |= set(found.variants)
            yield found


def proposed(con: sqlite3.Connection, kind: Kind, ctx: Context) -> list:
    return [found for subject in kind.standards for found in proposed_for(con, kind, ctx, subject)]


def row_of(con: sqlite3.Connection, subject: str, variant: str) -> Optional[list]:
    row = con.execute("SELECT standard, set_by FROM standards WHERE subject = ? AND variant = ?", (subject, variant)).fetchone()
    return list(row) if row else None


def put(con: sqlite3.Connection, subject: str, variant: str, row: Optional[list]) -> None:
    con.execute("DELETE FROM standards WHERE subject = ? AND variant = ?", (subject, variant))
    if row is not None:
        con.execute(
            "INSERT INTO standards(subject, variant, standard, set_by, set_at) VALUES (?, ?, ?, ?, ?)",
            (subject, variant, row[0], row[1], time.time()),
        )


def chained(con: sqlite3.Connection, subject: str, standards: set) -> dict:
    rows = con.execute("SELECT variant, standard, set_by FROM standards WHERE subject = ? AND set_by != ?", (subject, APART))
    return {variant: set_by for variant, standard, set_by in rows if standard in standards}


def remapped(con: sqlite3.Connection, found: Pending, set_by: str) -> dict:
    rows = {variant: [found.standard, by] for variant, by in chained(con, found.subject, set(found.variants)).items()}
    rows.update({variant: [found.standard, set_by] for variant in found.variants})
    if row_of(con, found.subject, found.standard) is not None:
        rows[found.standard] = None
    return rows


def kept_apart(found: Pending) -> dict:
    return {variant: [variant, APART] for variant in found.variants}


def rewrite_rows(con: sqlite3.Connection, subject: str, rows: dict) -> list:
    changes = []
    for variant, after in rows.items():
        before = row_of(con, subject, variant)
        if before != after:
            put(con, subject, variant, after)
            changes.append(Change(variant, "standard", {"subject": subject, "row": before}, {"subject": subject, "row": after}))
    return changes


def restandardize_fields(con: sqlite3.Connection, kind: Kind, table: dict) -> list:
    if not field_subjects(kind):
        return []
    changes = []
    for entity_id, fields_json in con.execute("SELECT id, fields_json FROM entities").fetchall():
        fields = tuple(json.loads(fields_json))
        named = standardized_fields(kind, fields, table)
        if named != fields:
            write_fields(con, entity_id, named)
            refresh_text(con, entity_id)
            changes.append(Change(entity_id, "fields", list(fields), list(named)))
    return changes


def tag_rows(con: sqlite3.Connection, entity_id: str) -> list:
    return [list(row) for row in con.execute("SELECT tag, set_by FROM tags WHERE id = ? ORDER BY tag", (entity_id,))]


def replace_tags(con: sqlite3.Connection, entity_id: str, entries) -> None:
    con.execute("DELETE FROM tags WHERE id = ?", (entity_id,))
    con.executemany(
        "INSERT INTO tags(id, tag, set_by, set_at) VALUES (?, ?, ?, ?)",
        [(entity_id, tag, set_by, time.time()) for tag, set_by in entries],
    )
    refresh_text(con, entity_id)


def retagged(entries: list, table: dict) -> list:
    kept = {}
    for tag, set_by in entries:
        kept.setdefault(table.get(tag, tag), set_by)
    return [[tag, set_by] for tag, set_by in kept.items()]


def retag(con: sqlite3.Connection, table: dict) -> list:
    tags = table.get(TAGS, {})
    ids = sorted({entity_id for entity_id, tag in con.execute("SELECT id, tag FROM tags") if tag in tags})
    changes = []
    for entity_id in ids:
        before = tag_rows(con, entity_id)
        after = retagged(before, tags)
        replace_tags(con, entity_id, after)
        changes.append(Change(entity_id, "tags", before, after))
    return changes


def as_pending(row: tuple) -> Pending:
    n, subject, standard, variants_json, shown_json, count = row
    return Pending(n, subject, standard, tuple(json.loads(variants_json)), tuple(json.loads(shown_json)), count)


def proposal_record(found: Pending) -> dict:
    return {
        "subject": found.subject,
        "standard": found.standard,
        "variants": list(found.variants),
        "shown": list(found.shown),
        "count": found.count,
    }


def insert_proposal(con: sqlite3.Connection, n: Optional[int], record: dict) -> None:
    con.execute(
        "INSERT OR REPLACE INTO proposals(n, subject, standard, variants_json, shown_json, count) VALUES (?, ?, ?, ?, ?, ?)",
        (
            n,
            record["subject"],
            record["standard"],
            json.dumps(record["variants"], ensure_ascii=False),
            json.dumps(record["shown"], ensure_ascii=False),
            record["count"],
        ),
    )


def store_proposals(con: sqlite3.Connection, found: list) -> None:
    con.execute("DELETE FROM proposals")
    for each in found:
        insert_proposal(con, None, proposal_record(each))


def all_proposals(con: sqlite3.Connection) -> list:
    return [as_pending(row) for row in con.execute(PROPOSALS + " ORDER BY subject, standard, n")]


def matches(found: Pending, typed: str) -> bool:
    haystack = " ".join((found.subject, found.standard, *found.shown)).casefold()
    return all(word in haystack for word in typed.casefold().split())


def proposals(con: sqlite3.Connection, typed: str = "") -> list:
    return [found for found in all_proposals(con) if matches(found, typed)]


def proposal(con: sqlite3.Connection, number: str) -> Optional[Pending]:
    row = con.execute(PROPOSALS + " WHERE n = ?", (number,)).fetchone() if number.isdigit() else None
    return as_pending(row) if row else None


def settled_proposal(con: sqlite3.Connection, found: Pending) -> bool:
    done = settled(con, found.subject)
    return all(variant in done for variant in found.shown)


def drop_settled_proposals(con: sqlite3.Connection) -> list:
    changes = []
    for found in all_proposals(con):
        if settled_proposal(con, found):
            con.execute("DELETE FROM proposals WHERE n = ?", (found.n,))
            changes.append(Change(str(found.n), "proposal", proposal_record(found), None))
    return changes


def rewrite(con: sqlite3.Connection, kind: Kind, rows_by_subject: list) -> list:
    changes = [change for subject, rows in rows_by_subject for change in rewrite_rows(con, subject, rows)]
    table = mapping(con)
    return changes + restandardize_fields(con, kind, table) + retag(con, table) + drop_settled_proposals(con)


def accept(con: sqlite3.Connection, kind: Kind, found: list, set_by: str = HAND) -> list:
    return rewrite(con, kind, [(each.subject, remapped(con, each, set_by)) for each in found])


def keep_apart(con: sqlite3.Connection, kind: Kind, found: list) -> list:
    return rewrite(con, kind, [(each.subject, kept_apart(each)) for each in found])


def refresh(con: sqlite3.Connection, kind: Kind, ctx: Context) -> int:
    if not kind.standards:
        return 0
    found = proposed(con, kind, with_standards(con, ctx))
    store_proposals(con, [each for each in found if not each.trivial])
    changes = accept(con, kind, [each for each in found if each.trivial], RULE)
    if changes:
        _journal.record(con, VERB, changes, undoable=True)
    con.commit()
    return len(found)


def chosen(con: sqlite3.Connection, ids) -> list:
    found = []
    for given in ids:
        if given.startswith(EVERY):
            found += proposals(con, given[len(EVERY) :])
        elif given.startswith(ONE):
            found += [p for p in (proposal(con, given[len(ONE) :]),) if p]
        elif given.startswith(CHOICE):
            number, standard = json.loads(given[len(CHOICE) :])
            found += [p.rechosen(standard) for p in (proposal(con, str(number)),) if p]
    return found


def choice_id(found: Pending, standard: str) -> str:
    return CHOICE + json.dumps([found.n, standard], ensure_ascii=False)


def undo_standard(con: sqlite3.Connection, change: Change) -> None:
    subject, before, after = change.before["subject"], change.before["row"], change.after["row"]
    automatic = before is None and after is not None and after[1] == RULE
    put(con, subject, change.id, [change.id, APART] if automatic else before)


def undo_fields(con: sqlite3.Connection, change: Change) -> None:
    if fields_of(con, change.id) is not None:
        write_fields(con, change.id, change.before)
        refresh_text(con, change.id)


def undo_tags(con: sqlite3.Connection, change: Change) -> None:
    replace_tags(con, change.id, change.before)


def undo_proposal(con: sqlite3.Connection, change: Change) -> None:
    insert_proposal(con, int(change.id), change.before)


UNDO = {"standard": undo_standard, "fields": undo_fields, "tags": undo_tags, "proposal": undo_proposal}


def undo(con: sqlite3.Connection, changes, ctx) -> None:
    for change in reversed(list(changes)):
        UNDO[change.kind_of_change](con, change)
