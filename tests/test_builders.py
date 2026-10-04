from __future__ import annotations

import base64
import xml.etree.ElementTree as ET
import zipfile

import pytest

from hoard.testing import make_epub, make_fb2

OPF_NS = {"opf": "http://www.idpf.org/2007/opf", "dc": "http://purl.org/dc/elements/1.1/"}
FB2_NS = {"fb": "http://www.gribuser.ru/xml/fictionbook/2.0"}


def opf_of(path):
    with zipfile.ZipFile(path) as book:
        return ET.fromstring(book.read("OEBPS/content.opf"))


def test_epub_starts_with_a_stored_mimetype(tmp_path):
    with zipfile.ZipFile(make_epub(tmp_path / "a.epub")) as book:
        first = book.infolist()[0]
    assert (first.filename, first.compress_type) == ("mimetype", zipfile.ZIP_STORED), (
        "an epub's first entry should be the uncompressed mimetype"
    )


@pytest.mark.parametrize(
    "arguments, xpath, expected",
    [
        ({"title": "Dune"}, ".//dc:title", ["Dune"]),
        ({"authors": ("A", "B")}, ".//dc:creator", ["A", "B"]),
        ({"date": "1965-08-01"}, ".//dc:date", ["1965-08-01"]),
        ({"title": None}, ".//dc:title", []),
    ],
)
def test_epub_metadata_lands_in_the_opf(tmp_path, arguments, xpath, expected):
    opf = opf_of(make_epub(tmp_path / "a.epub", **arguments))
    assert [node.text for node in opf.findall(xpath, OPF_NS)] == expected, f"{arguments} should appear at {xpath}"


@pytest.mark.parametrize(
    "style, xpath",
    [
        ("meta", ".//opf:meta[@name='cover']"),
        ("properties", ".//opf:item[@properties='cover-image']"),
    ],
)
def test_epub_cover_is_declared_in_either_style(tmp_path, style, xpath):
    opf = opf_of(make_epub(tmp_path / "a.epub", cover=b"\xff\xd8\xffjpeg", cover_style=style))
    assert opf.find(xpath, OPF_NS) is not None, f"a {style}-style cover should be declared"


@pytest.mark.parametrize("encoding", ["utf-8", "windows-1251"])
def test_fb2_parses_in_its_declared_encoding(tmp_path, encoding):
    path = make_fb2(tmp_path / "a.fb2", title="Отцы и дети", authors=(("Иван", "Тургенев"),), encoding=encoding)
    root = ET.parse(path).getroot()
    assert root.find(".//fb:book-title", FB2_NS).text == "Отцы и дети", f"a {encoding} fb2 should round-trip"


def test_fb2_cover_is_a_base64_binary(tmp_path):
    root = ET.parse(make_fb2(tmp_path / "a.fb2", cover=b"\xff\xd8\xffjpeg")).getroot()
    assert base64.b64decode(root.find("fb:binary", FB2_NS).text) == b"\xff\xd8\xffjpeg", "the cover should be embedded"
