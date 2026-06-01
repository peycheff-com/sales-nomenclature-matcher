from __future__ import annotations

import pytest

from matcher.pipeline import llm_client


def test_llm_available_rejects_missing_and_placeholder_keys(monkeypatch: pytest.MonkeyPatch):
    for key in ["", "none", "your-key-here", "sk-your-key-here"]:
        monkeypatch.setattr(llm_client.settings, "llm_provider", "openai")
        monkeypatch.setattr(llm_client.settings, "openai_api_key", key)
        assert llm_client.llm_available() is False


def test_llm_available_accepts_real_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(llm_client.settings, "llm_provider", "openai")
    monkeypatch.setattr(llm_client.settings, "openai_api_key", "real-key")

    assert llm_client.llm_available() is True


def test_clean_json_response_strips_json_fence_and_trailing_commas():
    content = """```json
    {"items": [{"id": 1,}],}
    ```"""

    assert llm_client.clean_json_response(content) == '{"items": [{"id": 1}]}'


def test_clean_json_response_strips_generic_fence():
    assert llm_client.clean_json_response("```\n{\"ok\": true}\n```") == '{"ok": true}'


def test_clean_json_response_trims_to_last_complete_json_object():
    assert llm_client.clean_json_response('{"ok": true} trailing text') == '{"ok": true}'


def test_clean_json_response_closes_truncated_array():
    assert llm_client.clean_json_response('[{"ok": true} trailing text') == '[{"ok": true}]'


def test_make_llm_client_sets_openrouter_headers_and_web_plugin(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict = {}

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(llm_client, "AsyncOpenAI", FakeAsyncOpenAI)
    monkeypatch.setattr(llm_client.settings, "llm_provider", "openrouter")
    monkeypatch.setattr(llm_client.settings, "openrouter_api_key", "router-key")
    monkeypatch.setattr(llm_client.settings, "llm_model", "openrouter-model")

    client, model, extra_body = llm_client.make_llm_client()

    assert isinstance(client, FakeAsyncOpenAI)
    assert model == "openrouter-model"
    assert captured["api_key"] == "router-key"
    assert captured["base_url"] == "https://openrouter.ai/api/v1"
    assert captured["default_headers"] == {
        "HTTP-Referer": "https://matcher.internal",
        "X-Title": "Sales Nomenclature Matcher",
    }
    assert extra_body == {"plugins": [{"id": "web"}]}


@pytest.mark.parametrize(
    ("provider", "model", "expected_extra_body"),
    [
        ("dashscope", "qwen-plus", {"enable_search": True}),
        ("local", "qwen2.5:7b-instruct", {"no_thinking": True}),
        ("openai", "gpt-4o-mini", {}),
    ],
)
def test_make_llm_client_sets_provider_specific_extra_body(
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    model: str,
    expected_extra_body: dict,
):
    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr(llm_client, "AsyncOpenAI", FakeAsyncOpenAI)
    monkeypatch.setattr(llm_client.settings, "llm_provider", provider)
    if provider != "local":
        monkeypatch.setattr(llm_client.settings, f"{provider}_api_key", "key")
    monkeypatch.setattr(llm_client.settings, "llm_model", model)

    client, resolved_model, extra_body = llm_client.make_llm_client()

    assert isinstance(client, FakeAsyncOpenAI)
    assert resolved_model == model
    assert extra_body == expected_extra_body


def test_make_llm_client_allows_model_override(monkeypatch: pytest.MonkeyPatch):
    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr(llm_client, "AsyncOpenAI", FakeAsyncOpenAI)
    monkeypatch.setattr(llm_client.settings, "llm_provider", "openai")
    monkeypatch.setattr(llm_client.settings, "openai_api_key", "key")
    monkeypatch.setattr(llm_client.settings, "llm_model", "default-model")

    _client, model, _extra_body = llm_client.make_llm_client(model_override="override-model")

    assert model == "override-model"
