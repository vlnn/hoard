from __future__ import annotations

from array import array
from typing import Callable, Optional

from hoard._http import request

BATCH = 16
TRIM = 1500


def chunks(texts: list, size: int = BATCH):
    for start in range(0, len(texts), size):
        yield texts[start : start + size]


def vectors_of(reply: dict) -> list:
    return [array("f", item["embedding"]) for item in sorted(reply["data"], key=lambda item: item["index"])]


def embed(url: str, model: str, texts, log: Optional[Callable[[str, dict, object], None]] = None) -> list:
    found = []
    for chunk in chunks([text[:TRIM] for text in texts]):
        sent = {"model": model, "input": chunk}
        reply = request(f"{url}/v1/embeddings", sent)
        if log:
            log("embeddings", sent, {"count": len(reply.get("data", []))})
        found += vectors_of(reply)
    return found
