from __future__ import annotations

import re
import unicodedata

WORD = re.compile(r"\w+")


def fold(text: str) -> str:
    if text.isascii():
        return text.lower()
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def words(text: str) -> list:
    return WORD.findall(fold(text))


def matches(typed: str, text: str) -> bool:
    have = words(text)
    return all(any(word.startswith(wanted) for word in have) for wanted in words(typed))
