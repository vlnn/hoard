from __future__ import annotations

import json
import sys
from typing import Callable, Optional

from hoard._http import ModelError, request

ATTEMPTS = 2
INSTRUCTIONS = "Answer only from the evidence, as JSON matching the schema. Leave a field empty when the evidence does not say."


def ignore(kind_of: str, sent: dict, received) -> None:
    pass


def payload(model: str, question: str, evidence: str, schema: dict) -> dict:
    return {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": INSTRUCTIONS},
            {"role": "user", "content": f"{question}\n\nEvidence:\n{evidence}"},
        ],
        "response_format": {"type": "json_schema", "json_schema": {"name": "answer", "schema": schema}},
    }


def parsed(reply: dict) -> Optional[dict]:
    try:
        answer = json.loads(reply["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    return answer if isinstance(answer, dict) else None


def ask(
    url: str,
    model: str,
    question: str,
    evidence: str,
    schema: dict,
    log: Optional[Callable[[str, dict, object], None]] = None,
    key: str = "",
) -> Optional[dict]:
    sent = payload(model, question, evidence, schema)
    for _ in range(ATTEMPTS):
        reply = request(f"{url}/v1/chat/completions", sent, key=key)
        answer = parsed(reply)
        (log or ignore)("chat", sent, answer if answer is not None else reply)
        if answer is not None:
            return answer
    print(f"ask: no JSON answer from {model} to {question!r}", file=sys.stderr)
    return None


__all__ = ["ModelError", "ask"]
