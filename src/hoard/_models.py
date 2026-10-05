from __future__ import annotations

import sqlite3
from typing import NamedTuple, Optional

from hoard import _db
from hoard.contract import Context, Kind, TextEmbedding

ROLES = ("chat", "embeddings")
PROBE_TIMEOUT = 3.0
OPENAI_PREFIX = "/v1"

SETTINGS = (
    ("hoard_chat_url", "Chat model server", "text", "A llama-server URL, e.g. http://localhost:8080; enables name and tag"),
    ("hoard_chat_key", "Chat server API key", "text", "Sent as a bearer token; leave empty if the server needs none"),
    ("hoard_embeddings_url", "Embeddings server", "text", "A llama-server URL serving embeddings; enables like"),
    ("hoard_embeddings_key", "Embeddings server API key", "text", "Sent as a bearer token; leave empty if the server needs none"),
    ("hoard_ask_on_update", "Ask and embed on update", "checkbox", "After each update, ask the models about new things"),
)


ASK_ON_UPDATE = "hoard_ask_on_update"


def roles_of(kind: Kind) -> tuple:
    wanted = {"chat": bool(kind.nameable or kind.tags), "embeddings": isinstance(kind.like, TextEmbedding)}
    return tuple(role for role in ROLES if wanted[role])


def settings_for(roles) -> tuple:
    return tuple(
        setting
        for setting in SETTINGS
        if any(setting[0].startswith(f"hoard_{role}_") for role in roles) or (roles and setting[0] == ASK_ON_UPDATE)
    )


class Server(NamedTuple):
    role: str
    url: str
    model: str
    key: str = ""


def url_of(ctx: Context, role: str) -> str:
    url = ctx.setting(f"hoard_{role}_url").strip().rstrip("/")
    return url[: -len(OPENAI_PREFIX)] if url.endswith(OPENAI_PREFIX) else url


def key_of(ctx: Context, role: str) -> str:
    return ctx.setting(f"hoard_{role}_key").strip()


def model_of(con: sqlite3.Connection, role: str) -> str:
    return _db.meta(con, f"model_{role}", "") or ""


def server(con: sqlite3.Connection, ctx: Context, role: str) -> Optional[Server]:
    url = url_of(ctx, role)
    return Server(role, url, model_of(con, role), key_of(ctx, role)) if url else None


def configured(ctx: Context) -> list:
    return [role for role in ROLES if url_of(ctx, role)]


def use(con: sqlite3.Connection, role: str, model: str) -> None:
    _db.set_meta(con, f"model_{role}", model)


def available(url: str, key: str = "", timeout: float = PROBE_TIMEOUT) -> list:
    from hoard._http import request

    return [item["id"] for item in request(f"{url}/v1/models", timeout=timeout, key=key).get("data", [])]
