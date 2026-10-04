from __future__ import annotations

import json


def sent(urlopen, n=0) -> dict:
    request = urlopen.call_args_list[n].args[0]
    return json.loads(request.data.decode("utf-8")) if request.data else {}


def chat_reply(content) -> dict:
    text = content if isinstance(content, str) else json.dumps(content)
    return {"choices": [{"message": {"role": "assistant", "content": text}}]}
