from types import SimpleNamespace

import pytest
from google.genai import errors as genai_errors

from backend.core import gemini_client


class FakeModels:
    def __init__(self, vectors: list[list[float]]):
        self.vectors = vectors
        self.calls = []

    def embed_content(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(embeddings=[SimpleNamespace(values=vector) for vector in self.vectors])


class FakeGeminiClient:
    def __init__(self, vectors: list[list[float]]):
        self.models = FakeModels(vectors)


@pytest.fixture(autouse=True)
def _clean_query_embedding_cache():
    """`embed_query` memoises per process, so a cached vector would leak between tests.

    Without this, a test that embeds a query successfully hands the next test a cache hit
    instead of the API call it is asserting on — the retry tests below share a query string
    and silently stopped exercising the retry loop.
    """
    gemini_client.clear_query_embedding_cache()
    yield
    gemini_client.clear_query_embedding_cache()


def _rate_limit_error(retry_delay: str = "5s") -> genai_errors.ClientError:
    """Shaped exactly like the real 429 response captured in production logs."""
    body = {
        "error": {
            "code": 429,
            "message": "You exceeded your current quota...",
            "status": "RESOURCE_EXHAUSTED",
            "details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": retry_delay}],
        }
    }
    return genai_errors.ClientError(429, body)


class FlakyModels:
    """Raises a 429 `fail_times` times, then returns `vectors` like FakeModels."""

    def __init__(self, vectors: list[list[float]], fail_times: int, error: Exception | None = None):
        self.vectors = vectors
        self.fail_times = fail_times
        self.error = error or _rate_limit_error()
        self.calls = 0

    def embed_content(self, **kwargs):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.error
        return SimpleNamespace(embeddings=[SimpleNamespace(values=vector) for vector in self.vectors])


class FakeFlakyGeminiClient:
    def __init__(self, models: FlakyModels):
        self.models = models


def test_embed_documents_uses_document_task_type(monkeypatch):
    fake_client = FakeGeminiClient(
        vectors=[
            [0.1, 0.2, 0.3],
            [0.4, 0.5, 0.6],
        ]
    )

    monkeypatch.setattr(gemini_client, "get_gemini_client", lambda: fake_client)
    monkeypatch.setattr(gemini_client.settings, "embedding_model", "gemini-embedding-001")
    monkeypatch.setattr(gemini_client.settings, "embedding_dimensions", 3)

    vectors = gemini_client.embed_documents(
        ["chunk mot", "chunk hai"],
        title="bang-gia.pdf",
    )

    assert vectors == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]

    call = fake_client.models.calls[0]
    assert call["model"] == "gemini-embedding-001"
    assert call["contents"] == ["chunk mot", "chunk hai"]
    assert call["config"].task_type == "RETRIEVAL_DOCUMENT"
    assert call["config"].title == "bang-gia.pdf"
    assert call["config"].output_dimensionality == 3


def test_embed_query_returns_one_vector(monkeypatch):
    fake_client = FakeGeminiClient(vectors=[[0.1, 0.2, 0.3]])

    monkeypatch.setattr(gemini_client, "get_gemini_client", lambda: fake_client)
    monkeypatch.setattr(gemini_client.settings, "embedding_dimensions", 3)

    vector = gemini_client.embed_query("Gia can 2PN bao nhieu?")

    assert vector == [0.1, 0.2, 0.3]
    assert fake_client.models.calls[0]["config"].task_type == "RETRIEVAL_QUERY"


def test_embed_documents_rejects_wrong_vector_dimension(monkeypatch):
    fake_client = FakeGeminiClient(vectors=[[0.1, 0.2]])

    monkeypatch.setattr(gemini_client, "get_gemini_client", lambda: fake_client)
    monkeypatch.setattr(gemini_client.settings, "embedding_dimensions", 3)

    with pytest.raises(gemini_client.GeminiEmbeddingError):
        gemini_client.embed_documents(["chunk"], title="bang-gia.pdf")


def test_embed_retries_past_a_rate_limit_and_succeeds(monkeypatch):
    models = FlakyModels(vectors=[[0.1, 0.2, 0.3]], fail_times=2, error=_rate_limit_error("7s"))
    monkeypatch.setattr(gemini_client, "get_gemini_client", lambda: FakeFlakyGeminiClient(models))
    monkeypatch.setattr(gemini_client.settings, "embedding_dimensions", 3)
    sleeps: list[float] = []
    monkeypatch.setattr(gemini_client.time, "sleep", sleeps.append)

    vector = gemini_client.embed_query("gia can 2PN bao nhieu?")

    assert vector == [0.1, 0.2, 0.3]
    assert models.calls == 3
    assert sleeps == [7.0, 7.0]


def test_embed_gives_up_after_max_attempts(monkeypatch):
    models = FlakyModels(vectors=[[0.1, 0.2, 0.3]], fail_times=99, error=_rate_limit_error("1s"))
    monkeypatch.setattr(gemini_client, "get_gemini_client", lambda: FakeFlakyGeminiClient(models))
    monkeypatch.setattr(gemini_client.settings, "embedding_dimensions", 3)
    monkeypatch.setattr(gemini_client.time, "sleep", lambda *_a: None)

    with pytest.raises(gemini_client.GeminiEmbeddingError):
        gemini_client.embed_query("gia can 2PN bao nhieu?")

    assert models.calls == gemini_client._EMBED_MAX_ATTEMPTS


def test_embed_does_not_retry_a_non_rate_limit_error(monkeypatch):
    """A 400 (bad request) or similar is a real error — retrying it would just waste
    time before failing the same way anyway."""
    bad_request = genai_errors.ClientError(400, {"error": {"code": 400, "message": "bad request"}})
    models = FlakyModels(vectors=[[0.1, 0.2, 0.3]], fail_times=99, error=bad_request)
    monkeypatch.setattr(gemini_client, "get_gemini_client", lambda: FakeFlakyGeminiClient(models))
    monkeypatch.setattr(gemini_client.settings, "embedding_dimensions", 3)
    monkeypatch.setattr(
        gemini_client.time, "sleep", lambda *_a: (_ for _ in ()).throw(AssertionError("should not sleep"))
    )

    with pytest.raises(gemini_client.GeminiEmbeddingError):
        gemini_client.embed_query("gia can 2PN bao nhieu?")

    assert models.calls == 1


def test_retry_delay_seconds_parses_the_api_suggestion():
    assert gemini_client.retry_delay_seconds(_rate_limit_error("21s")) == 21.0


def test_retry_delay_seconds_falls_back_when_shape_is_unexpected():
    malformed = genai_errors.ClientError(429, {"error": {"code": 429}})
    assert gemini_client.retry_delay_seconds(malformed) == gemini_client._DEFAULT_RETRY_DELAY_SECONDS


def test_repeated_query_is_embedded_once(monkeypatch):
    """Embedding is the dominant cost of retrieval; an identical query must not pay twice."""
    fake_client = FakeGeminiClient([[0.1, 0.2, 0.3]])
    monkeypatch.setattr(gemini_client, "get_gemini_client", lambda: fake_client)
    monkeypatch.setattr(gemini_client.settings, "embedding_model", "gemini-embedding-001")
    monkeypatch.setattr(gemini_client.settings, "embedding_dimensions", 3)

    first = gemini_client.embed_query("gia can 2PN")
    second = gemini_client.embed_query("gia can 2PN")

    assert first == second == [0.1, 0.2, 0.3]
    assert len(fake_client.models.calls) == 1


def test_cached_embedding_is_not_shared_between_callers(monkeypatch):
    """Callers hand the vector to Qdrant clients that may mutate it in place."""
    fake_client = FakeGeminiClient([[0.1, 0.2, 0.3]])
    monkeypatch.setattr(gemini_client, "get_gemini_client", lambda: fake_client)
    monkeypatch.setattr(gemini_client.settings, "embedding_model", "gemini-embedding-001")
    monkeypatch.setattr(gemini_client.settings, "embedding_dimensions", 3)

    first = gemini_client.embed_query("gia can 2PN")
    first.append(999.0)

    assert gemini_client.embed_query("gia can 2PN") == [0.1, 0.2, 0.3]


def test_different_queries_are_embedded_separately(monkeypatch):
    fake_client = FakeGeminiClient([[0.1, 0.2, 0.3]])
    monkeypatch.setattr(gemini_client, "get_gemini_client", lambda: fake_client)
    monkeypatch.setattr(gemini_client.settings, "embedding_model", "gemini-embedding-001")
    monkeypatch.setattr(gemini_client.settings, "embedding_dimensions", 3)

    gemini_client.embed_query("gia can 2PN")
    gemini_client.embed_query("gia can 3PN")

    assert len(fake_client.models.calls) == 2


def test_changing_the_model_does_not_serve_the_old_vector(monkeypatch):
    """A vector from another model/dimension is not interchangeable with this one."""
    fake_client = FakeGeminiClient([[0.1, 0.2, 0.3]])
    monkeypatch.setattr(gemini_client, "get_gemini_client", lambda: fake_client)
    monkeypatch.setattr(gemini_client.settings, "embedding_model", "gemini-embedding-001")
    monkeypatch.setattr(gemini_client.settings, "embedding_dimensions", 3)
    gemini_client.embed_query("gia can 2PN")

    monkeypatch.setattr(gemini_client.settings, "embedding_model", "gemini-embedding-002")
    gemini_client.embed_query("gia can 2PN")

    assert len(fake_client.models.calls) == 2


def test_cache_is_bounded(monkeypatch):
    fake_client = FakeGeminiClient([[0.1, 0.2, 0.3]])
    monkeypatch.setattr(gemini_client, "get_gemini_client", lambda: fake_client)
    monkeypatch.setattr(gemini_client.settings, "embedding_model", "gemini-embedding-001")
    monkeypatch.setattr(gemini_client.settings, "embedding_dimensions", 3)
    monkeypatch.setattr(gemini_client, "_QUERY_EMBED_CACHE_SIZE", 4)

    for index in range(10):
        gemini_client.embed_query(f"query {index}")

    assert len(gemini_client._query_embed_cache) <= 4
