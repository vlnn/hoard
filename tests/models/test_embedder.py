from __future__ import annotations

from array import array

import pytest
from wire import sent

from hoard import _embedder


def embeddings(*vectors):
    return {"data": [{"index": n, "embedding": list(v)} for n, v in reversed(list(enumerate(vectors)))]}


def test_embed_returns_float_arrays_in_input_order(replies):
    replies(embeddings([1.0, 0.0], [0.0, 1.0]))
    vectors = _embedder.embed("http://e:8081", "nomic", ["a", "b"])
    assert vectors == [array("f", [1.0, 0.0]), array("f", [0.0, 1.0])], "vectors should follow the input order"


def test_embed_posts_to_the_embeddings_route(replies):
    urlopen = replies(embeddings([1.0]))
    _embedder.embed("http://e:8081", "nomic", ["a"])
    assert urlopen.call_args.args[0].full_url == "http://e:8081/v1/embeddings", "embeddings use the OpenAI route"
    assert sent(urlopen) == {"model": "nomic", "input": ["a"]}, "the model and the inputs should be sent"


@pytest.mark.parametrize("count, calls", [(1, 1), (16, 1), (17, 2), (40, 3)])
def test_embed_sends_microbatches(replies, count, calls):
    urlopen = replies(*[embeddings(*[[1.0]] * min(16, count - 16 * n)) for n in range(calls)])
    assert len(_embedder.embed("http://e:8081", "nomic", ["x"] * count)) == count, "every text should get a vector"
    assert urlopen.call_count == calls, "texts should go sixteen at a time"


def test_long_texts_are_trimmed(replies):
    urlopen = replies(embeddings([1.0]))
    _embedder.embed("http://e:8081", "nomic", ["x" * 5000])
    assert len(sent(urlopen)["input"][0]) == _embedder.TRIM, "evidence should be trimmed before the call"
