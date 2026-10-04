from __future__ import annotations

import empty_kind
import pytest

from hoard.contract import Entity, Kind, Storage, Verb, roots_from
from hoard.testing import Conformance, FakeKind
from hoard.testing import conformance as suite
from hoard.testing.fake import write_note


class TestFakeKindConforms(Conformance):
    kind = FakeKind
    keystroke_banned = tuple(name for name in suite.KEYSTROKE_BANNED if name != "hoard.testing")

    def make_samples(self, storage, root):
        if storage != "shelf":
            return
        write_note(root, "dune", "Dune", "Frank Herbert", "1965")
        write_note(root, "nested/ubik", "Ubik", "Philip K. Dick", "1969")
        (root / "cover.jpg").write_bytes(b"\xff\xd8\xff")


class TestAnEmptyKindConforms(Conformance):
    kind = empty_kind.KIND


def test_private_imports_are_found(tmp_path):
    source = tmp_path / "kind.py"
    source.write_text("from hoard import _db\nimport hoard._index\nfrom hoard.contract import Kind\nimport hoard.api\n")
    assert suite.private_hoard_imports(str(source)) == ["hoard._db", "hoard._index"], (
        "imports of underscored hoard modules should be reported, public ones allowed"
    )


@pytest.mark.parametrize(
    "loaded, banned",
    [
        (["json", "zipfile"], ["zipfile"]),
        (["xml.etree.ElementTree", "xml"], ["xml", "xml.etree.ElementTree"]),
        (["hoard.testing.fake"], ["hoard.testing.fake"]),
        (["hoard.contract", "hoard.testingish", "sqlite3"], []),
    ],
)
def test_banned_modules_match_by_package(loaded, banned):
    assert suite.banned_among(loaded, suite.KEYSTROKE_BANNED) == banned, "a banned package should cover its submodules"


def a_broken_reader(path):
    return Entity("id", "Broken", fields=("only one",))


def test_a_reader_with_too_few_fields_fails_conformance(tmp_path):
    kind = Kind(
        name="broken",
        keyword="br",
        storages=(Storage("shelf", roots_from("shelf"), a_broken_reader),),
        fields=("author", "year"),
        evidence=lambda e: e.title,
    )
    (tmp_path / "file").write_text("x")
    entities = suite.read_samples(kind.storages[0], tmp_path)
    case = TestAnEmptyKindConforms()
    case.kind = kind
    with pytest.raises(AssertionError):
        case.test_every_entity_has_one_string_per_field(suite.Samples(kind, None, tuple(entities)))
        pytest.fail("a reader returning fewer values than fields should fail")


def test_a_verb_with_a_non_callable_undo_fails_conformance():
    case = TestAnEmptyKindConforms()
    case.kind = FakeKind._replace(verbs={"play": Verb("Play", run=print, undo="not callable")})
    with pytest.raises(AssertionError):
        case.test_verbs_declare_undo()
        pytest.fail("a verb whose undo is neither None nor callable should fail")


def forgetful_undo(changes, ctx):
    pass


def test_a_verb_whose_undo_leaves_traces_fails_conformance(tmp_path):
    from hoard.testing.fake import pack

    class Forgetful(Conformance):
        kind = FakeKind._replace(verbs={"pack": Verb("Pack", pack, forgetful_undo)}, commands={})

        def make_samples(self, storage, root):
            if storage == "shelf":
                write_note(root, "dune", "Dune")

    case = Forgetful()
    roots = {name: tmp_path / name for name in ("shelf", "satchel")}
    for name, root in roots.items():
        root.mkdir()
        case.make_samples(name, root)
    kind = suite.with_sample_roots(case.kind, roots)
    ctx = suite.Context(data=str(tmp_path), cache=str(tmp_path))
    with pytest.raises(AssertionError):
        case.test_undoable_verbs_undo_to_the_byte(suite.Samples(kind, ctx, (), tuple(roots.values())))
        pytest.fail("an undo that leaves the copy behind should fail the suite")
