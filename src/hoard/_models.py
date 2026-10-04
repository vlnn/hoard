from __future__ import annotations

import sqlite3
from typing import NamedTuple, Optional

from hoard import _db
from hoard.contract import Context

ROLES = ("chat", "embeddings")
PROBE_TIMEOUT = 1.0

SETTINGS = (
    ("hoard_chat_url", "Chat model server", "text", "A llama-server URL, e.g. http://localhost:8080; enables name and tag"),
    ("hoard_embeddings_url", "Embeddings server", "text", "A llama-server URL serving embeddings; enables like"),
    ("hoard_ask_on_update", "Ask and embed on update", "checkbox", "After each update, ask the models about new things"),
)


class Server(NamedTuple):
    role: str
    url: str
    model: str


def url_of(ctx: Context, role: str) -> str:
    return ctx.setting(f"hoard_{role}_url").strip().rstrip("/")


def model_of(con: sqlite3.Connection, role: str) -> str:
    return _db.meta(con, f"model_{role}", "") or ""


def server(con: sqlite3.Connection, ctx: Context, role: str) -> Optional[Server]:
    url = url_of(ctx, role)
    return Server(role, url, model_of(con, role)) if url else None


def configured(ctx: Context) -> list:
    return [role for role in ROLES if url_of(ctx, role)]


def use(con: sqlite3.Connection, role: str, model: str) -> None:
    _db.set_meta(con, f"model_{role}", model)


def available(url: str, timeout: float = PROBE_TIMEOUT) -> list:
    from hoard._http import request

    return [item["id"] for item in request(f"{url}/v1/models", timeout=timeout).get("data", [])]
