from __future__ import annotations

import argparse
import sys

from hoard import build


def arguments(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python3 -m hoard.build", description="Build this kind's Alfred workflow.")
    parser.add_argument("repo", nargs="?", default=".", help="the kind repository, the current folder by default")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="build, then answer an empty query from the bundle")
    mode.add_argument("--link", action="store_true", help="install a workflow symlinked to the checkouts")
    parser.add_argument("--into", help="Alfred's workflows folder, for --link")
    return parser.parse_args(argv)


def main(argv=None) -> None:
    given = arguments(argv)
    try:
        if given.link:
            print(build.link(given.repo, given.into))
        elif given.check:
            print(build.check(given.repo))
        else:
            print(build.bundle(given.repo))
    except build.BuildError as error:
        print(f"build failed: {error}", file=sys.stderr)
        sys.exit(1)


main()
