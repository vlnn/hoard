from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Optional

TIMEOUT = 60.0


class ModelError(Exception):
    pass


def as_request(url: str, payload: Optional[dict]) -> urllib.request.Request:
    if payload is None:
        return urllib.request.Request(url)
    data = json.dumps(payload).encode("utf-8")
    return urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})


def request(url: str, payload: Optional[dict] = None, timeout: float = TIMEOUT) -> dict:
    try:
        with urllib.request.urlopen(as_request(url, payload), timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise ModelError(f"{url}: {error}") from error
