from __future__ import annotations

from wire import chat_reply, sent

from hoard import _oracle

SCHEMA = {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]}


def ask(log=None):
    return _oracle.ask("http://m:8080", "qwen", "What is the title?", "Dune by Frank Herbert", SCHEMA, log=log)


def test_ask_requests_an_answer_in_the_schema(replies):
    urlopen = replies(chat_reply({"title": "Dune"}))
    assert ask() == {"title": "Dune"}, "a well-formed answer should come back as a dict"
    payload = sent(urlopen)
    assert urlopen.call_args.args[0].full_url == "http://m:8080/v1/chat/completions", "chat goes to the OpenAI route"
    assert payload["model"] == "qwen", "the chosen model should be named"
    assert payload["response_format"] == {"type": "json_schema", "json_schema": {"name": "answer", "schema": SCHEMA}}, (
        "the answer should be constrained to the schema"
    )
    assert "Dune by Frank Herbert" in payload["messages"][-1]["content"], "the evidence should be sent"


def test_malformed_json_is_asked_once_more(replies):
    replies(chat_reply("{not json"), chat_reply({"title": "Dune"}))
    assert ask() == {"title": "Dune"}, "one retry should rescue a malformed answer"


def test_two_malformed_answers_give_up(replies):
    urlopen = replies(chat_reply("{not json"), chat_reply("[1, 2]"))
    assert ask() is None, "after the retry the entity should be skipped"
    assert urlopen.call_count == 2, "there should be exactly one retry"


def test_every_exchange_is_logged(replies, mocker):
    log = mocker.Mock()
    replies(chat_reply({"title": "Dune"}))
    ask(log)
    kind_of, request, response = log.call_args.args
    assert (kind_of, request["model"], response["title"]) == ("chat", "qwen", "Dune"), "the log should get both sides"
