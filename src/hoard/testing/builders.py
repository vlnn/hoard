from __future__ import annotations

import os
from typing import Mapping, Union

Content = Union[str, bytes]


def write_file(path: str, content: Content) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mode = "wb" if isinstance(content, bytes) else "w"
    with open(path, mode) as handle:
        handle.write(content)


def temp_tree(root, spec: Mapping[str, Content]) -> str:
    for relative, content in spec.items():
        write_file(os.path.join(str(root), relative), content)
    return str(root)
