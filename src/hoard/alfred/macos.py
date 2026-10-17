from __future__ import annotations

import subprocess


def applescript_string(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def osascript(script: str, check: bool) -> None:
    subprocess.run(["osascript", "-e", script], check=check, capture_output=True)


def open(path: str) -> None:
    subprocess.run(["open", path], check=False)


def reveal(path: str) -> None:
    subprocess.run(["open", "-R", path], check=False)


def trash(path: str) -> None:
    osascript(f'tell application "Finder" to delete POSIX file "{applescript_string(path)}"', check=True)


def copy(text: str) -> None:
    subprocess.run(["pbcopy"], input=text, text=True, check=True)


def notify(text: str, title: str) -> None:
    try:
        osascript(f'display notification "{applescript_string(text)}" with title "{applescript_string(title)}"', check=False)
    except FileNotFoundError:
        pass
