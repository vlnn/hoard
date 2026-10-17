from __future__ import annotations

import io
import json
import urllib.error

import pytest

from hoard.alfred import chat


def test_a_post_sends_json_and_parses_the_reply(replies):
    urlopen = replies({"ok": True})
    assert chat.request("http://m:8080/v1/x", {"a": 1}) == {"ok": True}, "the reply body should be parsed as JSON"
    request = urlopen.call_args.args[0]
    assert (request.full_url, request.get_method(), request.data) == ("http://m:8080/v1/x", "POST", b'{"a": 1}'), (
        "the payload should be posted as JSON"
    )
    assert request.get_header("Content-type") == "application/json", "the request should declare JSON"


@pytest.mark.parametrize("key, header", [("secret", "Bearer secret"), ("", None)])
def test_an_api_key_is_sent_as_a_bearer_token(replies, key, header):
    urlopen = replies({"ok": True})
    chat.request("http://m:8080/v1/models", key=key)
    assert urlopen.call_args.args[0].get_header("Authorization") == header, "a key should travel as a bearer token"


def test_a_get_sends_no_body(replies):
    urlopen = replies({"data": []})
    chat.request("http://m:8080/v1/models")
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
    with pytest.raises(chat.ModelError):
        chat.request("http://m:8080/v1/x", {"a": 1})


SERVER = chat.Server("http://127.0.0.1:8080", "oracle", "")
MESSAGES = [{"role": "system", "content": "s"}, {"role": "user", "content": "q"}]


def sse(*chunks):
    lines = [b"data: " + json.dumps({"choices": [{"delta": {"content": c}}]}).encode() for c in chunks]
    return [*lines, b"", b"data: [DONE]"]


def streamed(mocker, lines):
    opened = mocker.MagicMock()
    opened.__enter__.return_value = iter(lines)
    return mocker.patch("urllib.request.urlopen", return_value=opened)


@pytest.mark.parametrize(
    "lines, expected",
    [
        (sse("Hel", "lo"), ["Hel", "lo"]),
        ([b": keep-alive", b"data: [DONE]"], []),
        ([b'data: {"choices": [{"delta": {"role": "assistant"}}]}'], []),
        ([b"data: not json"], []),
    ],
)
def test_deltas_are_the_content_pieces_of_an_event_stream(lines, expected):
    assert list(chat.deltas(lines)) == expected, f"{lines} should yield {expected}"


def test_an_error_event_is_a_model_error():
    with pytest.raises(chat.ModelError, match="context too long"):
        list(chat.deltas([b'data: {"error": {"message": "context too long"}}']))


def test_stream_feeds_the_text_so_far_as_it_arrives(mocker):
    urlopen = streamed(mocker, sse("You ", "read ", "docs."))
    seen = []
    assert chat.stream(SERVER, MESSAGES, seen.append) == "You read docs.", "the whole answer comes back at the end"
    assert seen == ["You ", "You read ", "You read docs."], "each step gets the text so far"
    body = json.loads(urlopen.call_args.args[0].data)
    assert (body["stream"], body["model"], body["messages"]) == (True, "oracle", MESSAGES), "the request streams, names the model, carries the messages"


def test_a_server_with_no_model_name_leaves_it_to_the_server(mocker):
    urlopen = streamed(mocker, sse("ok"))
    chat.stream(chat.Server("http://m:8080"), MESSAGES)
    assert "model" not in json.loads(urlopen.call_args.args[0].data), "a single-model server needs no name"


@pytest.mark.parametrize(
    "failure, reason",
    [
        (urllib.error.URLError("refused"), "refused"),
        (TimeoutError("slow"), "slow"),
        (urllib.error.HTTPError("http://m", 401, "nope", {}, io.BytesIO()), "HTTP 401 nope"),
    ],
)
def test_streaming_failures_are_model_errors_too(mocker, failure, reason):
    mocker.patch("urllib.request.urlopen", side_effect=failure)
    with pytest.raises(chat.ModelError) as caught:
        chat.stream(SERVER, MESSAGES)
    assert caught.value.reason == reason, "the reason is kept apart from the url"


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Three things.", "Three things."),
        ("<think>hmm</think>\nThree things.", "Three things."),
        ("<think>still thin", ""),
        ("  spaced ", "spaced"),
    ],
)
def test_without_thinking_hides_what_a_thinking_model_leaks(text, expected):
    assert chat.without_thinking(text) == expected, f"{text!r} should show as {expected!r}"


def test_respond_is_the_visible_part_of_the_stream(mocker):
    streamed(mocker, sse("<think>x</think>", "done"))
    assert chat.respond(SERVER, MESSAGES) == "done", "the thinking never reaches the caller"


@pytest.mark.parametrize("outcome, reachable", [({"data": []}, True), (urllib.error.URLError("refused"), False)])
def test_reachable_probes_the_models_endpoint(replies, outcome, reachable):
    replies(outcome)
    assert chat.reachable(SERVER) is reachable, "a server that lists its models is reachable"
