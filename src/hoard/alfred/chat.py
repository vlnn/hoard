from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Callable, Iterable, Iterator, NamedTuple, Optional

TIMEOUT = 60.0
PROBE_TIMEOUT = 3.0
THINKING = re.compile(r"<think>.*?</think>", re.DOTALL)
UNCLOSED_THINKING = re.compile(r"<think>.*\Z", re.DOTALL)
NO_THINKING = {"chat_template_kwargs": {"enable_thinking": False}}

OnText = Callable[[str], None]


class ModelError(Exception):
    def __init__(self, reason: str, url: str = ""):
        super().__init__(f"{url}: {reason}" if url else reason)
        self.reason = reason


class Server(NamedTuple):
    url: str
    model: str = ""
    key: str = ""


def reason_of(error: Exception) -> str:
    if isinstance(error, urllib.error.HTTPError):
        return f"HTTP {error.code} {error.reason}"
    if isinstance(error, urllib.error.URLError):
        return str(error.reason)
    if isinstance(error, ValueError):
        return "the reply was not JSON"
    return str(error) or type(error).__name__


def headers_for(payload: Optional[dict], key: str) -> dict:
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    return {**headers, "Authorization": f"Bearer {key}"} if key else headers


def as_request(url: str, payload: Optional[dict], key: str = "") -> urllib.request.Request:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    return urllib.request.Request(url, data=data, headers=headers_for(payload, key))


def request(url: str, payload: Optional[dict] = None, timeout: float = TIMEOUT, key: str = "") -> dict:
    try:
        with urllib.request.urlopen(as_request(url, payload, key), timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise ModelError(reason_of(error), url) from error


def reachable(server: Server, timeout: float = PROBE_TIMEOUT) -> bool:
    try:
        request(f"{server.url}/v1/models", timeout=timeout, key=server.key)
    except ModelError:
        return False
    return True


def chat_payload(server: Server, messages: list, options: dict) -> dict:
    body = {"messages": messages, **options}
    return {**body, "model": server.model} if server.model else body


def refused(line: str) -> None:
    try:
        error = json.loads(line[5:])["error"]
    except (ValueError, KeyError, TypeError):
        return
    raise ModelError(error.get("message") if isinstance(error, dict) else str(error))


def deltas(lines: Iterable[bytes]) -> Iterator[str]:
    for raw in lines:
        line = raw.decode("utf-8", "replace").strip()
        if not line.startswith("data:") or line == "data: [DONE]":
            continue
        try:
            delta = json.loads(line[5:])["choices"][0]["delta"].get("content")
        except (ValueError, KeyError, IndexError, TypeError):
            refused(line)
            continue
        if delta:
            yield delta


def stream(server: Server, messages: list, on_text: Optional[OnText] = None, timeout: float = TIMEOUT, **options) -> str:
    url = f"{server.url}/v1/chat/completions"
    body = chat_payload(server, messages, {**NO_THINKING, **options, "stream": True})
    text = ""
    try:
        with urllib.request.urlopen(as_request(url, body, server.key), timeout=timeout) as response:
            for delta in deltas(response):
                text += delta
                if on_text:
                    on_text(text)
    except (urllib.error.URLError, OSError) as error:
        raise ModelError(reason_of(error), url) from error
    return text


def without_thinking(text: str) -> str:
    return UNCLOSED_THINKING.sub("", THINKING.sub("", text)).strip()


def respond(server: Server, messages: list, on_text: Optional[OnText] = None, **options) -> str:
    return without_thinking(stream(server, messages, on_text, **options))
