from __future__ import annotations

import json
import sqlite3
from collections import Counter

from hoard import _answers, _fold, _models, _names, _questions, _rows, _search, _standards, _tags
from hoard.contract import Context, Kind
from hoard.items import Head, Item, Mod

CHOICE = "tagset:"
EVERY = "#*"
STANDARD_MOD = Mod("cmd", "pick_standard", "Choose the standard spelling, or keep them apart")


def ask_head(con: sqlite3.Connection, kind: Kind, ctx: Context, question: str) -> list:
    if not _models.configured(ctx) or "chat" not in _models.configured(ctx):
        return []
    waiting = len(_answers.stale(con, question))
    if not waiting:
        return []
    title = f"Ask about {_rows.counted(kind, waiting)}"
    return [Head("ask", title, "the model runs in the background", verb="ask", arg=f"ask:{question}")]


def percent(answer: dict) -> str:
    return f"{round(float(answer.get('confidence') or 0) * 100)}%"


def suggestion_item(kind: Kind, suggestion) -> Item:
    title, fields = _names.overlaid(kind, suggestion.title, suggestion.fields, suggestion.answer)
    named = [fields[kind.fields.index(field)] for field in kind.nameable]
    detail = " · ".join([percent(suggestion.answer), *(value for value in named if value), f"was {suggestion.title}"])
    return Item(suggestion.id, title, detail, verb="accept")


def name_rows(con, kind: Kind, ctx: Context, words: list) -> tuple:
    typed = " ".join(words)
    waiting = _names.pending(con, kind, typed)
    heads = ask_head(con, kind, ctx, _questions.NAME)
    if waiting:
        heads.append(Head("accept", f"Accept {len(waiting)}", "↩ accepts every suggestion below", verb="accept", arg=f"names:{typed}"))
    rows = tuple(heads) + tuple(suggestion_item(kind, s) for s in waiting[: _search.LIMIT])
    return rows or (Head("none", "Nothing to name"),)


def choice(target: str, tag: str) -> str:
    return CHOICE + json.dumps([target, tag], ensure_ascii=False)


def every_target(words: list) -> str:
    return EVERY + "+".join(words)


def target_words(target: str) -> str:
    return target[len(EVERY) :].replace("+", " ")


def untagged_ids(con: sqlite3.Connection, typed: str) -> list:
    return _search.ids(con, typed, untagged=True)


def picker_head(con: sqlite3.Connection, kind: Kind, target: str) -> Head:
    if target.startswith(EVERY):
        return Head("picker", f"Tag all {len(untagged_ids(con, target_words(target)))}", "pick a tag")
    row = con.execute("SELECT title FROM entities WHERE id = ?", (target[1:],)).fetchone()
    return Head("picker", row[0] if row else "Nothing to tag", "pick a tag")


def guess_first(tags: list, guessed) -> list:
    return sorted(tags, key=lambda tag: tag != guessed.tag) if guessed else tags


def choice_note(tag: str, current: set, guessed) -> str:
    notes = ["current"] if tag in current else []
    notes += [f"suggested · {guessed.percent}"] if guessed and tag == guessed.tag else []
    return " · ".join(notes)


def picker_rows(con, kind: Kind, ctx: Context, target: str, typed: str) -> tuple:
    single = not target.startswith(EVERY)
    current = {tag for tag, _ in _tags.tags_of(con, target[1:])} if single else set()
    guessed = _tags.guess(con, target[1:]) if single and picker_target_exists(con, target) else None
    tags = guess_first(_questions.tag_list(kind, ctx), guessed)
    shown = [tag for tag in tags if typed.lower() in tag.lower()]
    items = [Item(choice(target, tag), tag, choice_note(tag, current, guessed), verb="set_tag") for tag in shown]
    if typed and typed.lower() not in (tag.lower() for tag in tags):
        items.append(Item(choice(target, typed), f"New tag: {typed}", verb="set_tag"))
    return (picker_head(con, kind, target),) + tuple(items)


def picker_target_exists(con: sqlite3.Connection, target: str) -> bool:
    return con.execute("SELECT 1 FROM entities WHERE id = ?", (target[1:],)).fetchone() is not None


def tag_item(con: sqlite3.Connection, kind: Kind, ctx: Context, row) -> Item:
    item = _rows.entity_item(kind, row, verb="pick", ctx=ctx)
    guessed = _tags.guess(con, item.id)
    return item._replace(subtitle=f"{guessed.tag}? {guessed.percent} · {item.subtitle}") if guessed else item


def tally(con: sqlite3.Connection, ids: list) -> str:
    counts = Counter(_tags.suggestion(con, entity_id) for entity_id in ids)
    ordered = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    return " · ".join(f"{tag} {count}" for tag, count in ordered)


def suggested_ids(con: sqlite3.Connection, typed: str) -> list:
    return [entity_id for entity_id in untagged_ids(con, typed) if _tags.suggestion(con, entity_id)]


def tag_heads(con, kind: Kind, ctx: Context, words: list, total: int) -> list:
    typed = " ".join(words)
    heads = ask_head(con, kind, ctx, _questions.TAG)
    guessed = suggested_ids(con, typed)
    if guessed:
        heads.append(Head("accept tags", f"Accept {len(guessed)} suggested", tally(con, guessed), verb="accept_tags", arg=f"suggested:{typed}"))
    heads.append(Head("tag all", f"Tag all {total}", "pick one tag for every row below", verb="pick", arg=f"pick:{every_target(words)}"))
    return heads


def tag_rows(con, kind: Kind, ctx: Context, words: list) -> tuple:
    if words and words[0].startswith("#"):
        return picker_rows(con, kind, ctx, words[0], " ".join(words[1:]))
    typed = " ".join(words)
    total = _search.count(con, typed, untagged=True)
    if not total:
        return (Head("none", "Nothing to tag"),)
    rows = _fold.fold(con, kind, ctx, _search.search(con, typed, untagged=True, order=_search.order_of(kind)))
    return tuple(tag_heads(con, kind, ctx, words, total)) + tuple(tag_item(con, kind, ctx, row) for row in rows)


def proposal_item(kind: Kind, found) -> Item:
    detail = [found.subject, ", ".join(found.shown)] + ([_rows.counted(kind, found.count)] if found.count else [])
    return Item(f"{_standards.ONE}{found.n}", found.standard, " · ".join(detail), verb="standardize", mods=(STANDARD_MOD,))


def nothing_to_standardize() -> tuple:
    return (Head("none", "Nothing to standardize"),)


def spelling_item(found, spelling: str) -> Item:
    note = "current standard" if spelling == found.standard else ""
    return Item(_standards.choice_id(found, spelling), spelling, note, verb="standardize")


def standard_picker_rows(con: sqlite3.Connection, number: str) -> tuple:
    found = _standards.proposal(con, number)
    if found is None:
        return nothing_to_standardize()
    head = Head("picker", f"{found.subject}: {found.standard}", "pick the standard spelling")
    spellings = tuple(spelling_item(found, spelling) for spelling in (found.standard, *found.shown))
    apart = Item(f"{_standards.ONE}{found.n}", "Keep apart", "these stay different spellings", verb="keep_apart")
    return (head, *spellings, apart)


def std_rows(con, kind: Kind, ctx: Context, words: list) -> tuple:
    if words and words[0].startswith("#"):
        return standard_picker_rows(con, words[0][1:])
    typed = " ".join(words)
    waiting = _standards.proposals(con, typed)
    if not waiting:
        return nothing_to_standardize()
    head = Head(
        "accept standards",
        f"Accept {len(waiting)}",
        "↩ makes every spelling below standard",
        verb="standardize",
        arg=f"{_standards.EVERY}{typed}",
    )
    return (head,) + tuple(proposal_item(kind, found) for found in waiting[: _search.LIMIT])
