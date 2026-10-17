from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Callable, Iterable, Iterator, Optional

from hoard.alfred.chat import ModelError

SOURCE = Path(__file__).with_name("apple.swift")
NAME = "hoard-apple"
TIMEOUT = 180
TOOLS_MISSING = "Compiling the Apple helper needs the Command Line Tools: xcode-select --install"
NO_ANSWER = "The Apple model did not answer in time"

OnText = Callable[[str], None]


class AppleError(ModelError):
    pass


def binary(data: str) -> Path:
    return Path(data) / "bin" / NAME


def compile_command(target: Path) -> list:
    return ["swiftc", "-O", "-parse-as-library", "-o", str(target), str(SOURCE)]


def stale(target: Path) -> bool:
    return not target.exists() or target.stat().st_mtime < SOURCE.stat().st_mtime


def respond(messages: list, data: str, on_text: Optional[OnText] = None) -> str:
    target = binary(data)
    if stale(target):
        build(target)
    instructions = "\n".join(m["content"] for m in messages if m["role"] == "system")
    prompt = "\n".join(m["content"] for m in messages if m["role"] != "system")
    return stream([str(target), instructions], prompt, on_text).strip()


def build(target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(compile_command(target), capture_output=True, text=True, check=True, timeout=TIMEOUT)
    except FileNotFoundError:
        raise AppleError(TOOLS_MISSING) from None
    except subprocess.CalledProcessError as error:
        raise AppleError(error.stderr.strip() or "swiftc failed") from None
    except subprocess.TimeoutExpired:
        raise AppleError("swiftc did not finish in time") from None


def stream(argv: list, stdin: str, on_text: Optional[OnText]) -> str:
    helper = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert helper.stdin and helper.stdout and helper.stderr
    helper.stdin.write(stdin)
    helper.stdin.close()
    text = ""
    for text in snapshots(helper.stdout):
        if on_text:
            on_text(text)
    try:
        code = helper.wait(timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        helper.kill()
        raise AppleError(NO_ANSWER) from None
    if code:
        raise AppleError(helper.stderr.read().strip() or f"{argv[0]} failed")
    return text


def snapshots(lines: Iterable[str]) -> Iterator[str]:
    for line in lines:
        try:
            snapshot = json.loads(line)
        except ValueError:
            continue
        if isinstance(snapshot, str):
            yield snapshot
