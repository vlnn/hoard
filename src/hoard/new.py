from __future__ import annotations

import argparse
import getpass
import os
import shutil
import string
from pathlib import Path
from typing import Optional

TEMPLATE = Path(__file__).parent / "template"
PLACEHOLDER = "__kind__"
SUFFIX = ".tmpl"


def check_name(kind: str) -> None:
    if not (kind.isidentifier() and kind.islower()):
        raise ValueError(f"{kind!r} should be a lowercase identifier, since it becomes the package name")


def library_checkout() -> Path:
    root = Path(__file__).resolve().parents[2]
    if (root / "pyproject.toml").is_file() and (root / "src" / "hoard").is_dir():
        return root
    raise LookupError("hoard is not running from a checkout; pass --hoard with the library's path")


def target_of(template_file: Path, kind: str) -> Path:
    relative = str(template_file.relative_to(TEMPLATE)).replace(PLACEHOLDER, kind)
    return Path(relative[: -len(SUFFIX)] if relative.endswith(SUFFIX) else relative)


def template_files() -> list:
    return sorted(p for p in TEMPLATE.rglob("*") if p.is_file() and "__pycache__" not in p.parts)


def write_one(template_file: Path, target: Path, values: dict) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if template_file.suffix == SUFFIX:
        text = string.Template(template_file.read_text(encoding="utf-8")).safe_substitute(values)
        target.write_text(text, encoding="utf-8")
    else:
        shutil.copyfile(template_file, target)


def write_kind_repository(
    kind: str,
    into,
    keyword: Optional[str] = None,
    title: Optional[str] = None,
    bundle_prefix: str = "com.example",
    author: Optional[str] = None,
    hoard_source=None,
) -> Path:
    check_name(kind)
    root = Path(into) / f"hoard-{kind}"
    if root.exists():
        raise FileExistsError(f"{root} already exists")
    values = {
        "kind": kind,
        "keyword": keyword or kind[:2],
        "title": title or kind.replace("_", " ").title(),
        "bundle_prefix": bundle_prefix,
        "author": author if author is not None else getpass.getuser(),
        "hoard_source": os.path.relpath(Path(hoard_source or library_checkout()).resolve(), Path(into).resolve() / root.name),
    }
    for template_file in template_files():
        write_one(template_file, root / target_of(template_file, kind), values)
    return root


def arguments(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python3 -m hoard.new", description="Write a new kind repository.")
    parser.add_argument("kind", help="the kind's package name, e.g. shelf")
    parser.add_argument("--keyword", help="the Alfred keyword; the first two letters by default")
    parser.add_argument("--title", help="the workflow's display name")
    parser.add_argument("--bundle-prefix", default="com.example", help="reverse-DNS prefix of the bundle id")
    parser.add_argument("--into", default=".", help="folder to create hoard-<kind> in")
    parser.add_argument("--hoard", help="path to the library checkout the kind depends on")
    return parser.parse_args(argv)


def main(argv=None) -> None:
    given = arguments(argv)
    root = write_kind_repository(
        given.kind, given.into, given.keyword, given.title, given.bundle_prefix, hoard_source=given.hoard
    )
    print(f"wrote {root}; next: cd {root} && uv sync && make test")


if __name__ == "__main__":
    main()
