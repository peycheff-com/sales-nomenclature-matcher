from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock

import pytest

from matcher.indexing import embedder


class _FakeVector(list):
    def tolist(self) -> list[float]:
        return list(self)


class _FakeSentenceTransformer:
    def __init__(self, model: str) -> None:
        self.model = model

    def encode(
        self,
        texts: list[str],
        normalize_embeddings: bool,
        show_progress_bar: bool,
    ) -> list[_FakeVector]:
        assert normalize_embeddings is True
        assert show_progress_bar is False
        return [_FakeVector([float(len(text)), 1.0]) for text in texts]


@pytest.mark.asyncio
async def test_local_embedder_uses_sentence_transformers(monkeypatch: pytest.MonkeyPatch):
    module = types.ModuleType("sentence_transformers")
    module.SentenceTransformer = _FakeSentenceTransformer
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)
    monkeypatch.setattr(embedder.settings, "embedding_provider", "local")
    monkeypatch.setattr(embedder.settings, "embedding_model", "fake-model")
    monkeypatch.setattr(embedder.settings, "embedding_dimensions", 2)
    monkeypatch.setattr(embedder, "_local_embedding_model", None, raising=False)

    vectors = await embedder.embed_texts(["abc", "abcd"], batch_size=1)

    assert vectors == [[3.0, 1.0], [4.0, 1.0]]


@pytest.mark.asyncio
async def test_local_embedder_tracks_tokens_and_tolerates_dimension_mismatch(
    monkeypatch: pytest.MonkeyPatch,
):
    class Tracker:
        def __init__(self) -> None:
            self.records: list[dict] = []

        def record(self, **kwargs) -> None:
            self.records.append(kwargs)

    module = types.ModuleType("sentence_transformers")
    module.SentenceTransformer = _FakeSentenceTransformer
    tracker = Tracker()
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)
    monkeypatch.setattr(embedder, "_local_embedding_model", None, raising=False)

    vectors = await embedder._embed_texts_local(
        ["one two"],
        model="fake-model",
        dimensions=3,
        batch_size=1,
        token_tracker=tracker,
    )

    assert vectors == [[7.0, 1.0]]
    assert tracker.records == [
        {
            "operation": "embed",
            "provider": "local",
            "model": "fake-model",
            "prompt_tokens": 4,
            "total_tokens": 4,
        }
    ]


@pytest.mark.asyncio
async def test_local_embedder_reports_missing_optional_dependency(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    monkeypatch.setattr(embedder.settings, "embedding_provider", "local")
    monkeypatch.setattr(embedder.settings, "embedding_model", "fake-model")
    monkeypatch.setattr(embedder, "_local_embedding_model", None, raising=False)

    with pytest.raises(RuntimeError, match="uv sync --extra local"):
        await embedder.embed_texts(["abc"])


def test_get_client_rejects_disabled_provider(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(embedder.settings, "embedding_provider", "none")
    embedder.reset_client()

    with pytest.raises(RuntimeError, match="Semantic search disabled"):
        embedder._get_client()


def test_get_client_requires_api_key_for_hosted_provider(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(embedder.settings, "embedding_provider", "openai")
    monkeypatch.setattr(
        type(embedder.settings),
        "active_embedding_api_key",
        property(lambda _self: ""),
    )
    embedder.reset_client()

    with pytest.raises(RuntimeError, match="No API key configured"):
        embedder._get_client()


def test_get_client_initializes_openrouter_headers(monkeypatch: pytest.MonkeyPatch):
    created: dict[str, object] = {}

    class FakeOpenAI:
        def __init__(self, **kwargs) -> None:
            created.update(kwargs)

    monkeypatch.setattr(embedder, "AsyncOpenAI", FakeOpenAI)
    monkeypatch.setattr(embedder.settings, "embedding_provider", "openrouter")
    monkeypatch.setattr(embedder.settings, "embedding_model", "embed-model")
    monkeypatch.setattr(
        type(embedder.settings),
        "active_embedding_api_key",
        property(lambda _self: "key"),
    )
    monkeypatch.setattr(
        type(embedder.settings),
        "active_embedding_base_url",
        property(lambda _self: "https://api"),
    )
    embedder.reset_client()

    assert isinstance(embedder._get_client(), FakeOpenAI)
    assert created["api_key"] == "key"
    assert created["base_url"] == "https://api"
    assert created["default_headers"] == {
        "HTTP-Referer": "https://matcher.internal",
        "X-Title": "Sales Nomenclature Matcher",
    }


@pytest.mark.asyncio
async def test_embed_texts_openai_compatible_records_usage_and_retries(
    monkeypatch: pytest.MonkeyPatch,
):
    class Item:
        def __init__(self, embedding: list[float]) -> None:
            self.embedding = embedding

    class Usage:
        prompt_tokens = 7
        total_tokens = 9

    class Response:
        data = [Item([1.0]), Item([2.0])]
        usage = Usage()

    class Embeddings:
        def __init__(self) -> None:
            self.create = AsyncMock(side_effect=[RuntimeError("temporary"), Response()])

    class Client:
        def __init__(self) -> None:
            self.embeddings = Embeddings()

    class Tracker:
        def __init__(self) -> None:
            self.records: list[dict] = []

        def record(self, **kwargs) -> None:
            self.records.append(kwargs)

    client = Client()
    tracker = Tracker()
    monkeypatch.setattr(embedder, "_get_client", lambda: client)
    monkeypatch.setattr(embedder.settings, "embedding_provider", "openai")
    monkeypatch.setattr(embedder.settings, "embedding_dimensions", 1)
    monkeypatch.setattr(embedder.asyncio, "sleep", AsyncMock())

    vectors = await embedder.embed_texts(
        ["a", "b"],
        model="model",
        batch_size=2,
        max_retries=2,
        token_tracker=tracker,
    )

    assert vectors == [[1.0], [2.0]]
    assert client.embeddings.create.await_count == 2
    assert tracker.records == [
        {
            "operation": "embed",
            "provider": "openai",
            "model": "model",
            "prompt_tokens": 7,
            "total_tokens": 9,
        }
    ]


@pytest.mark.asyncio
async def test_embed_texts_openai_compatible_retries_between_batches(
    monkeypatch: pytest.MonkeyPatch,
):
    class Item:
        def __init__(self, embedding: list[float]) -> None:
            self.embedding = embedding

    class Response:
        def __init__(self, value: float) -> None:
            self.data = [Item([value])]
            self.usage = None

    class Embeddings:
        def __init__(self) -> None:
            self.create = AsyncMock(
                side_effect=[Response(1.0), RuntimeError("temporary"), Response(2.0)]
            )

    class Client:
        def __init__(self) -> None:
            self.embeddings = Embeddings()

    client = Client()
    sleep = AsyncMock()
    monkeypatch.setattr(embedder, "_get_client", lambda: client)
    monkeypatch.setattr(embedder.settings, "embedding_provider", "openai")
    monkeypatch.setattr(embedder.asyncio, "sleep", sleep)

    vectors = await embedder.embed_texts(
        ["a", "b"],
        model="model",
        dimensions=None,
        batch_size=1,
        max_retries=2,
    )

    assert vectors == [[1.0], [2.0]]
    assert sleep.await_args_list[0].args == (0.1,)
    assert sleep.await_args_list[1].args == (1,)


@pytest.mark.asyncio
async def test_embed_texts_openai_compatible_raises_after_final_retry(
    monkeypatch: pytest.MonkeyPatch,
):
    class Embeddings:
        def __init__(self) -> None:
            self.create = AsyncMock(side_effect=RuntimeError("permanent"))

    class Client:
        def __init__(self) -> None:
            self.embeddings = Embeddings()

    monkeypatch.setattr(embedder, "_get_client", lambda: Client())
    monkeypatch.setattr(embedder.settings, "embedding_provider", "openai")

    with pytest.raises(RuntimeError, match="permanent"):
        await embedder.embed_texts(["a"], max_retries=1)


@pytest.mark.asyncio
async def test_embed_single_returns_first_embedding(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(embedder, "embed_texts", AsyncMock(return_value=[[0.4, 0.5]]))

    assert await embedder.embed_single("query") == [0.4, 0.5]


@pytest.mark.asyncio
async def test_google_embedder_posts_batches_and_tracks_tokens(monkeypatch: pytest.MonkeyPatch):
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"embeddings": [{"values": [1.0, 2.0]}, {"values": [3.0, 4.0]}]}

    class Client:
        def __init__(self) -> None:
            self.posts: list[tuple[str, dict, float]] = []

        async def __aenter__(self) -> Client:
            return self

        async def __aexit__(self, *exc_info) -> None:
            return None

        async def post(self, url: str, json: dict, timeout: float) -> Response:
            self.posts.append((url, json, timeout))
            return Response()

    class Tracker:
        def __init__(self) -> None:
            self.records: list[dict] = []

        def record(self, **kwargs) -> None:
            self.records.append(kwargs)

    client = Client()
    tracker = Tracker()
    monkeypatch.setattr(embedder.httpx, "AsyncClient", lambda: client)
    monkeypatch.setattr(
        type(embedder.settings),
        "active_embedding_api_key",
        property(lambda _self: "google-key"),
    )

    vectors = await embedder._embed_texts_google(
        ["first text", "second"],
        model="text-embedding-004",
        dimensions=2,
        batch_size=200,
        max_retries=1,
        token_tracker=tracker,
    )

    assert vectors == [[1.0, 2.0], [3.0, 4.0]]
    url, payload, timeout = client.posts[0]
    assert "models/text-embedding-004:batchEmbedContents?key=google-key" in url
    assert payload["requests"][0]["outputDimensionality"] == 2
    assert timeout == 30.0
    assert tracker.records[0]["provider"] == "google"
    assert tracker.records[0]["prompt_tokens"] == 6


@pytest.mark.asyncio
async def test_embed_texts_dispatches_to_google_provider(monkeypatch: pytest.MonkeyPatch):
    google_embed = AsyncMock(return_value=[[0.1]])
    monkeypatch.setattr(embedder.settings, "embedding_provider", "google")
    monkeypatch.setattr(embedder, "_embed_texts_google", google_embed)

    assert await embedder.embed_texts(["text"], model="model", dimensions=2) == [[0.1]]
    google_embed.assert_awaited_once_with(["text"], "model", 2, 100, 3, None)


@pytest.mark.asyncio
async def test_google_embedder_requires_api_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        type(embedder.settings),
        "active_embedding_api_key",
        property(lambda _self: ""),
    )

    with pytest.raises(RuntimeError, match="No API key configured for Google"):
        await embedder._embed_texts_google(["text"], "model", None, 1, 1)


@pytest.mark.asyncio
async def test_google_embedder_retries_and_pauses_between_batches(monkeypatch: pytest.MonkeyPatch):
    class Response:
        def __init__(self, value: float) -> None:
            self.value = value

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"embeddings": [{"values": [self.value]}]}

    class Client:
        def __init__(self) -> None:
            self.post = AsyncMock(
                side_effect=[Response(1.0), RuntimeError("temporary"), Response(2.0)]
            )

        async def __aenter__(self) -> Client:
            return self

        async def __aexit__(self, *exc_info) -> None:
            return None

    client = Client()
    sleep = AsyncMock()
    monkeypatch.setattr(embedder.httpx, "AsyncClient", lambda: client)
    monkeypatch.setattr(embedder.asyncio, "sleep", sleep)
    monkeypatch.setattr(
        type(embedder.settings),
        "active_embedding_api_key",
        property(lambda _self: "google-key"),
    )

    vectors = await embedder._embed_texts_google(
        ["one", "two"],
        model="models/text-embedding-004",
        dimensions=None,
        batch_size=1,
        max_retries=2,
    )

    assert vectors == [[1.0], [2.0]]
    assert sleep.await_args_list[0].args == (0.5,)
    assert sleep.await_args_list[1].args == (1,)


@pytest.mark.asyncio
async def test_google_embedder_raises_after_final_retry(monkeypatch: pytest.MonkeyPatch):
    class Client:
        def __init__(self) -> None:
            self.post = AsyncMock(side_effect=RuntimeError("permanent"))

        async def __aenter__(self) -> Client:
            return self

        async def __aexit__(self, *exc_info) -> None:
            return None

    monkeypatch.setattr(embedder.httpx, "AsyncClient", lambda: Client())
    monkeypatch.setattr(
        type(embedder.settings),
        "active_embedding_api_key",
        property(lambda _self: "google-key"),
    )

    with pytest.raises(RuntimeError, match="permanent"):
        await embedder._embed_texts_google(["one"], "model", None, 1, 1)
