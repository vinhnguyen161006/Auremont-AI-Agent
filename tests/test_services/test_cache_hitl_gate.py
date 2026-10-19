"""A cache hit must still pass the HITL gate.

A cache hit goes straight to END (`_route_after_cache`), so `_cache_check` is the ONLY place
the HITL gate can still fire for an answer taken from the cache. `_store_cache` used to refuse
every `requires_hitl` answer, and in a real-estate knowledge base almost every answer touches a
price — so the cache collection was never even created. The trade-off now: cache answers that
touch prices too, but re-run RiskCheck when they are read back.
"""

from backend.core.enums import DocumentVisibility
from backend.services.chat import agent_pipeline
from backend.services.chat.cache_service import CachedAnswer

PRICE_ANSWER = "- Căn 2PN The Zurich giá 2,5 tỷ đồng, đã bao gồm VAT."
SAFE_ANSWER = "- Tiện ích nội khu gồm bể bơi bốn mùa và phòng gym."


def _cached(answer: str) -> CachedAnswer:
    return CachedAnswer(answer=answer, citations=[{"document_id": 1, "title": "t"}], verifier_score=0.95)


def _result(**kw):
    base = dict(draft_answer=PRICE_ANSWER, citations=[], verifier_score=0.95, requires_hitl=True)
    base.update(kw)
    return agent_pipeline.PipelineResult(**base)


def test_cached_price_answer_still_raises_hitl(monkeypatch):
    """Điểm mấu chốt: câu chạm giá lấy từ cache vẫn phải bắt Sale xác nhận."""
    monkeypatch.setattr(agent_pipeline.cache_service, "lookup_cache", lambda *a, **kw: _cached(PRICE_ANSWER))

    result = agent_pipeline._cache_check({"query": "giá 2PN The Zurich?"})

    assert result["used_cache"] is True
    assert result["requires_hitl"] is True


def test_cached_safe_answer_does_not_raise_hitl(monkeypatch):
    """Not every cached answer raises HITL — an amenity description still goes straight through."""
    monkeypatch.setattr(agent_pipeline.cache_service, "lookup_cache", lambda *a, **kw: _cached(SAFE_ANSWER))

    result = agent_pipeline._cache_check({"query": "tiện ích có gì?"})

    assert result["used_cache"] is True
    assert result["requires_hitl"] is False


def test_hitl_verdict_is_recomputed_not_read_from_the_cache_row(monkeypatch):
    """RiskCheck runs on the cached TEXT ITSELF and does not trust the flag stored with it.

    If someone mistakenly writes a price answer to the cache as if it were harmless, the
    gate must still fire.
    """
    monkeypatch.setattr(
        agent_pipeline.cache_service,
        "lookup_cache",
        lambda *a, **kw: _cached("- Khách đặt cọc 200 triệu để giữ chỗ."),
    )

    assert agent_pipeline._cache_check({"query": "đặt cọc bao nhiêu?"})["requires_hitl"] is True


def test_price_answer_is_now_cached(monkeypatch):
    """This is what unlocks the whole feature: price answers used to never be written."""
    stored: dict = {}
    monkeypatch.setattr(agent_pipeline.cache_service, "store_cache", lambda **kw: stored.update(kw))

    agent_pipeline._store_cache("giá 2PN?", _result(), None, DocumentVisibility.INTERNAL)

    assert stored.get("answer") == PRICE_ANSWER


def test_answer_with_listings_is_not_cached(monkeypatch):
    """CachedAnswer cannot carry listings — caching it would lose the unit cards."""
    stored: dict = {}
    monkeypatch.setattr(agent_pipeline.cache_service, "store_cache", lambda **kw: stored.update(kw))

    agent_pipeline._store_cache(
        "còn căn 2PN nào?",
        _result(listings=[{"project_name": "The Zurich", "price_range": "2,5 tỷ đồng"}]),
        None,
        DocumentVisibility.INTERNAL,
    )

    assert stored == {}


def test_answer_with_images_is_not_cached(monkeypatch):
    stored: dict = {}
    monkeypatch.setattr(agent_pipeline.cache_service, "store_cache", lambda **kw: stored.update(kw))

    agent_pipeline._store_cache(
        "cho xem mặt bằng", _result(images=[{"url": "http://x/a.jpg"}]), None, DocumentVisibility.INTERNAL
    )

    assert stored == {}


def test_low_scoring_answer_is_not_cached(monkeypatch):
    """Cache một câu trả lời tệ chỉ là nhân bản cái tệ đó."""
    stored: dict = {}
    monkeypatch.setattr(agent_pipeline.cache_service, "store_cache", lambda **kw: stored.update(kw))

    agent_pipeline._store_cache("giá 2PN?", _result(verifier_score=0.3), None, DocumentVisibility.INTERNAL)

    assert stored == {}
