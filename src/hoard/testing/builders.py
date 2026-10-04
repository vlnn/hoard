from __future__ import annotations

import base64
import os
import zipfile
from typing import Mapping, Optional, Sequence, Union
from xml.sax.saxutils import escape, quoteattr

from hoard.contract import Context

Content = Union[str, bytes]

CONTAINER = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>"""

OPF = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="{version}" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
{metadata}
  </metadata>
  <manifest>
{manifest}
  </manifest>
  <spine>
{spine}
  </spine>
</package>"""

CHAPTER = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>{n}</title></head>
<body><p>{text}</p></body></html>"""

FB2 = """<?xml version="1.0" encoding="{encoding}"?>
<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0" xmlns:l="http://www.w3.org/1999/xlink">
  <description><title-info>
{title_info}
  </title-info></description>
  <body><section><p>{body}</p></section></body>
{binary}
</FictionBook>"""


def write_file(path: str, content: Content) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    mode = "wb" if isinstance(content, bytes) else "w"
    with open(path, mode) as handle:
        handle.write(content)


def temp_tree(root, spec: Mapping[str, Content]) -> str:
    for relative, content in spec.items():
        write_file(os.path.join(str(root), relative), content)
    return str(root)


def make_context(base, **config: str) -> Context:
    data = os.path.join(str(base), "data")
    cache = os.path.join(str(base), "cache")
    os.makedirs(data, exist_ok=True)
    os.makedirs(cache, exist_ok=True)
    return Context(data=data, cache=cache, config=dict(config))


def element(tag: str, value: Optional[str], **attributes: str) -> str:
    attrs = "".join(f" {name.replace('_', '-')}={quoteattr(v)}" for name, v in attributes.items())
    return f"    <{tag}{attrs}>{escape(value)}</{tag}>" if value is not None else f"    <{tag}{attrs}/>"


def opf_metadata(title, authors, date, series, series_index, cover, cover_style) -> str:
    lines = [element("dc:identifier", "urn:uuid:hoard-fixture", id="uid")]
    lines += [element("dc:title", title)] if title is not None else []
    lines += [element("dc:creator", author) for author in authors]
    lines += [element("dc:date", date)] if date else []
    lines += [element("meta", None, name="calibre:series", content=series)] if series else []
    lines += [element("meta", None, name="calibre:series_index", content=series_index)] if series_index else []
    lines += [element("meta", None, name="cover", content="cover-image")] if cover and cover_style == "meta" else []
    return "\n".join(lines)


def opf_manifest(chapters: Sequence[str], cover: Optional[bytes], cover_style: str) -> str:
    lines = [element("item", None, id=f"ch{n}", href=f"text/ch{n}.xhtml", media_type="application/xhtml+xml") for n in range(len(chapters))]
    if cover:
        properties = {"properties": "cover-image"} if cover_style == "properties" else {}
        lines.append(element("item", None, id="cover-image", href="images/cover.jpg", media_type="image/jpeg", **properties))
    return "\n".join(lines)


def opf_spine(chapters: Sequence[str]) -> str:
    return "\n".join(element("itemref", None, idref=f"ch{n}") for n in range(len(chapters)))


def make_epub(
    path,
    title: Optional[str] = "Untitled",
    authors: Sequence[str] = ("Anonymous",),
    date: Optional[str] = None,
    series: Optional[str] = None,
    series_index: Optional[str] = None,
    chapters: Sequence[str] = ("Once upon a time.",),
    cover: Optional[bytes] = None,
    cover_style: str = "meta",
) -> str:
    path = str(path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    opf = OPF.format(
        version="3.0" if cover_style == "properties" else "2.0",
        metadata=opf_metadata(title, authors, date, series, series_index, cover, cover_style),
        manifest=opf_manifest(chapters, cover, cover_style),
        spine=opf_spine(chapters),
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        archive.writestr("META-INF/container.xml", CONTAINER, compress_type=zipfile.ZIP_DEFLATED)
        archive.writestr("OEBPS/content.opf", opf, compress_type=zipfile.ZIP_DEFLATED)
        for n, chapter in enumerate(chapters):
            archive.writestr(f"OEBPS/text/ch{n}.xhtml", CHAPTER.format(n=n, text=escape(chapter)), compress_type=zipfile.ZIP_DEFLATED)
        if cover:
            archive.writestr("OEBPS/images/cover.jpg", cover)
    return path


def fb2_author(first: str, last: str) -> str:
    return f"    <author>\n  {element('first-name', first)}\n  {element('last-name', last)}\n    </author>"


def fb2_title_info(title, authors, date, series, number, cover) -> str:
    lines = [fb2_author(first, last) for first, last in authors]
    lines += [element("book-title", title)] if title is not None else []
    lines += [element("date", date)] if date else []
    lines += ['    <coverpage><image l:href="#cover.jpg"/></coverpage>'] if cover else []
    if series:
        lines.append(element("sequence", None, name=series, **({"number": number} if number else {})))
    return "\n".join(lines)


def fb2_binary(cover: Optional[bytes]) -> str:
    if not cover:
        return ""
    encoded = base64.b64encode(cover).decode("ascii")
    return f'  <binary id="cover.jpg" content-type="image/jpeg">{encoded}</binary>'


def make_fb2(
    path,
    title: Optional[str] = "Untitled",
    authors: Sequence[tuple] = (("Anon", "Ymous"),),
    date: Optional[str] = None,
    series: Optional[str] = None,
    number: Optional[str] = None,
    body: str = "Once upon a time.",
    cover: Optional[bytes] = None,
    encoding: str = "utf-8",
) -> str:
    document = FB2.format(
        encoding=encoding,
        title_info=fb2_title_info(title, authors, date, series, number, cover),
        body=escape(body),
        binary=fb2_binary(cover),
    )
    write_file(str(path), document.encode(encoding))
    return str(path)
