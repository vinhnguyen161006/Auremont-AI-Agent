"""When rerank falls back to the heuristic, it must leave a mark in the trace.

The Cohere trial key allows only 10 calls per minute, so under real load the fallback path is
taken constantly. If it were not recorded, an Admin's trace would look exactly like a normal
run, with nothing saying the cross-encoder never ran.
"""

import pytest

from backend.core import tracing
from backend.core.cohere_client import CohereRerankError
from backend.core.config import settings
from backend.services.chat import rag_service


def _hits(*contents: str) -> list[dict]:
    return [
        {"document_id": i, "title": "t", "page": 1, "content": c, "score": 0.9 - i * 0.1}
        for i, c in enumerate(contents)
    ]


def _rerank_steps(run) -> list[dict]:
    return [s for s in run.as_dict()["steps"] if s["name"] == "rerank"]


@pytest.fixture
def traced(monkeypatch):
    """Enable tracing and open a run, returning that run so the test can read its steps back."""
    monkeypatch.setattr(settings, "tracing_enabled", True)
    return tracing.start_run(query_len=10, project_id=None, clearance="internal")


@pytest.fixture
def cohere_on(monkeypatch):
    monkeypatch.setattr(settings, "rerank_enabled", True)
    monkeypatch.setattr(settings, "cohere_api_key", "test-key")


def test_successful_cohere_rerank_is_recorded(traced, cohere_on, monkeypatch):
    monkeypatch.setattr(rag_service, "cohere_rerank", lambda q, docs, **kw: [(1, 0.9), (0, 0.2)])

    rag_service._rerank("giá 2PN", _hits("a", "b"))

    step = _rerank_steps(traced)[0]
    assert step["ranker"] == "cohere"
    assert step["candidate_count"] == 2
    assert "degraded" not in step


def test_fallback_is_recorded_as_degraded(traced, cohere_on, monkeypatch):
    """This is the most important line: a rate limit must never be silent."""

    def _boom(*_a, **_kw):
        raise CohereRerankError("429 rate limited")

    monkeypatch.setattr(rag_service, "cohere_rerank", _boom)

    rag_service._rerank("giá 2PN", _hits("a", "b"))

    step = _rerank_steps(traced)[0]
    assert step["ranker"] == "heuristic"
    assert step["degraded"] is True


def test_rerank_switched_off_is_not_reported_as_degraded(traced, monkeypatch):
    """Turning rerank off is a configuration choice, not an incident — do not raise a false alarm."""
    monkeypatch.setattr(settings, "rerank_enabled", False)

    rag_service._rerank("giá 2PN", _hits("a", "b"))

    step = _rerank_steps(traced)[0]
    assert step["ranker"] == "heuristic"
    assert step["degraded"] is False


def test_answer_still_returned_when_cohere_fails(cohere_on, monkeypatch):
    """Being observable is one thing; breaking the result is another."""

    def _boom(*_a, **_kw):
        raise CohereRerankError("429")

    monkeypatch.setattr(rag_service, "cohere_rerank", _boom)

    ranked = rag_service._rerank("căn 3PN", _hits("suat 2PN gia tot", "bang gia 3PN"))

    assert [h["content"] for h in ranked] == ["bang gia 3PN", "suat 2PN gia tot"]
