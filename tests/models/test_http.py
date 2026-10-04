from __future__ import annotations

import io
import urllib.error

import pytest

from hoard import _http


def test_a_post_sends_json_and_parses_the_reply(replies):
    urlopen = replies({"ok": True})
    assert _http.request("http://m:8080/v1/x", {"a": 1}) == {"ok": True}, "the reply body should be parsed as JSON"
    request = urlopen.call_args.args[0]
    assert (request.full_url, request.get_method(), request.data) == ("http://m:8080/v1/x", "POST", b'{"a": 1}'), (
        "the payload should be posted as JSON"
    )
    assert request.get_header("Content-type") == "application/json", "the request should declare JSON"


def test_a_get_sends_no_body(replies):
    urlopen = replies({"data": []})
    _http.request("http://m:8080/v1/models")
    assert urlopen.call_args.args[0].get_method() == "GET", "a request without payload should be a GET"


@pytest.mark.parametrize(
    "failure",
    [
        urllib.error.URLError("refused"),
        urllib.error.HTTPError("http://m", 500, "boom", {}, io.BytesIO()),
        TimeoutError("slow"),
        b"not json",
    ],
)
def test_every_failure_becomes_a_model_error(replies, failure):
    replies(failure)
    with pytest.raises(_http.ModelError):
        _http.request("http://m:8080/v1/x", {"a": 1})
