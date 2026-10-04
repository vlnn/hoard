from __future__ import annotations

import pytest

from hoard import _models
from hoard.contract import Context


def ctx_with(**config):
    return Context(data="", cache="", config=config)


@pytest.mark.parametrize(
    "config, role, url",
    [
        ({"hoard_chat_url": "http://m:8080/"}, "chat", "http://m:8080"),
        ({"hoard_chat_url": "  "}, "chat", ""),
        ({}, "embeddings", ""),
        ({"hoard_embeddings_url": "http://e:8081"}, "embeddings", "http://e:8081"),
        ({"hoard_embeddings_url": "http://e:8081/v1"}, "embeddings", "http://e:8081"),
        ({"hoard_embeddings_url": "http://e:8081/v1/"}, "embeddings", "http://e:8081"),
        ({"hoard_chat_url": "https://box.local/llm/v1"}, "chat", "https://box.local/llm"),
    ],
)
def test_server_urls_come_from_the_workflow_settings(config, role, url):
    assert _models.url_of(ctx_with(**config), role) == url, "the URL should be the setting, trimmed"


def test_a_server_names_its_chosen_model(tmp_db):
    ctx = ctx_with(hoard_chat_url="http://m:8080")
    assert _models.server(tmp_db, ctx, "chat") == _models.Server("chat", "http://m:8080", ""), "no model chosen yet"
    _models.use(tmp_db, "chat", "qwen")
    assert _models.server(tmp_db, ctx, "chat").model == "qwen", "the chosen model should be remembered"


def test_no_url_means_no_server(tmp_db):
    assert _models.server(tmp_db, ctx_with(), "chat") is None, "without a URL there is no server"


def test_available_models_come_from_v1_models(replies):
    urlopen = replies({"object": "list", "data": [{"id": "qwen"}, {"id": "llama"}]})
    assert _models.available("http://m:8080") == ["qwen", "llama"], "model ids should be listed in order"
    assert urlopen.call_args.args[0].full_url == "http://m:8080/v1/models", "models come from the OpenAI route"
