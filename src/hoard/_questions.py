from __future__ import annotations

from hoard.contract import TAGS, Context, Kind

NAME = "name"
TAG = "tag"
CONFIDENT = 0.8
STRING = {"type": "string"}
CONFIDENCE = {"type": "number", "minimum": 0, "maximum": 1}


def noun(kind: Kind) -> str:
    return kind.labels.get("one", "item")


def tag_list(kind: Kind, ctx: Context) -> list:
    return list(dict.fromkeys(ctx.standard(TAGS, tag) for tag in kind.tags(ctx))) if kind.tags else []


def enabled(kind: Kind, ctx: Context) -> list:
    return [question for question, on in ((NAME, bool(kind.nameable)), (TAG, bool(tag_list(kind, ctx)))) if on]


def name_schema(kind: Kind) -> dict:
    properties = {"title": STRING, **{field: STRING for field in kind.nameable}, "confidence": CONFIDENCE}
    return {"type": "object", "properties": properties, "required": list(properties)}


def tag_schema(kind: Kind, ctx: Context) -> dict:
    properties = {"tag": {"type": "string", "enum": tag_list(kind, ctx)}, "confidence": CONFIDENCE}
    return {"type": "object", "properties": properties, "required": list(properties)}


def schema(kind: Kind, ctx: Context, question: str) -> dict:
    return name_schema(kind) if question == NAME else tag_schema(kind, ctx)


def text(kind: Kind, question: str) -> str:
    if question == NAME:
        wanted = ", ".join(["title", *kind.nameable])
        return f"What are the {wanted} of this {noun(kind)}? Give your confidence from 0 to 1."
    return f"Which one tag fits this {noun(kind)} best? Give your confidence from 0 to 1."


def confident(answer: dict) -> bool:
    return bool(answer.get("accepted")) or float(answer.get("confidence") or 0) >= CONFIDENT
