from __future__ import annotations

import subprocess
import sys

ALFRED = 'tell application id "com.runningwithcrayons.Alfred" to search "{}"'


def quoted(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def reopen(query: str) -> None:
    try:
        subprocess.run(["osascript", "-e", ALFRED.format(quoted(query))], check=False)
    except FileNotFoundError:
        print(f"reopen: no osascript here; wanted {query!r}", file=sys.stderr)
