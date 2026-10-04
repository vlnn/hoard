from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Optional

TIMEOUT = 60.0


class ModelError(Exception):
    def __init__(self, reason: str, url: str = ""):
        super().__init__(f"{url}: {reason}" if url else reason)
        self.reason = reason


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
