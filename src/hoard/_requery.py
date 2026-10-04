from __future__ import annotations

import subprocess

ALFRED = 'tell application id "com.runningwithcrayons.Alfred" to search "{}"'


def quoted(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def reopen(query: str) -> None:
    subprocess.run(["osascript", "-e", ALFRED.format(quoted(query))], check=False)
