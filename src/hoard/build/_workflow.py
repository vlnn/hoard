from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import tomllib

SETTING_TYPES = ("lines", "text", "folder", "checkbox")


class BuildError(Exception):
    pass


@dataclass(frozen=True)
class Setting:
    variable: str
    label: str
    type: str
    description: str = ""
    default: object = ""


@dataclass(frozen=True)
class Workflow:
    kind: str
    name: str
    bundleid: str
    description: str = ""
    createdby: str = ""
    configuration: tuple = ()


def read_toml(path: Path) -> dict:
    with open(path, "rb") as handle:
        return tomllib.load(handle)


def read_setting(entry: dict) -> Setting:
    setting = Setting(**entry)
    if setting.type not in SETTING_TYPES:
        raise BuildError(f"{setting.variable}: type should be one of {', '.join(SETTING_TYPES)}")
    return setting


def read_workflow(repo) -> Workflow:
    data = read_toml(Path(repo) / "workflow" / "plist.toml")
    settings = tuple(read_setting(entry) for entry in data.pop("configuration", []))
    return Workflow(configuration=settings, **data)


def kind_version(repo) -> str:
    return read_toml(Path(repo) / "pyproject.toml").get("project", {}).get("version", "0")
