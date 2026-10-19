"""Long-term memory where it meets the pipeline: the prompt, and the shared cache.

The remembering rules live in tests/test_services/test_memory_service.py. What matters
here is that a personalised answer never escapes into the cache other people read.
"""

from backend.ai import prompts
from backend.services.chat import agent_pipeline, memory_service

PROFILE = "- Loai can thuong quan tam: 2PN"


def test_profile_reaches_the_prompt():
    prompt = prompts.build_prompt("Gia can 3PN?", [], [], False, False, profile=PROFILE)

    assert "GHI NHỚ VỀ NGƯỜI HỎI" in prompt
    assert "2PN" in prompt


def test_prompt_forbids_answering_out_of_the_profile():
    """The remembered budget is a hint about the person, not project data."""
    prompt = prompts.build_prompt("Gia can 3PN?", [], [], False, False, profile=PROFILE)

    assert "KHÔNG phải dữ liệu dự án" in prompt
    assert "câu hỏi thắng" in prompt


def test_no_profile_leaves_the_prompt_byte_identical():
    """Khong co ho so => prompt y het truoc khi co long-term memory."""
    without = prompts.build_prompt("Gia can 3PN?", [], [], False, False)
    with_empty = prompts.build_prompt("Gia can 3PN?", [], [], False, False, profile="")

    assert without == with_empty
    assert "GHI NHỚ" not in without


def test_profile_sits_above_the_conversation_history():
    """Who is asking comes first, then what they are saying in this session."""
    history = [{"sender": "sale", "content": "Gia can 2PN?"}]

    prompt = prompts.build_prompt("Con 3PN?", [], [], False, False, history=history, profile=PROFILE)

    assert prompt.index("GHI NHỚ VỀ NGƯỜI HỎI") < prompt.index("LỊCH SỬ HỘI THOẠI")


def test_cache_is_skipped_for_a_personalised_question(monkeypatch):
    """The cache is shared by everyone — a personalised answer must not be served from it."""

    def fail(*_args, **_kwargs):
        raise AssertionError("cache must not be consulted for a personalised question")

    monkeypatch.setattr(agent_pipeline.cache_service, "lookup_cache", fail)

    assert agent_pipeline._cache_check({"query": "Gia can 2PN?", "memory_profile": PROFILE}) == {"used_cache": False}


def test_cache_still_serves_a_question_from_someone_with_no_profile(monkeypatch):
    """The cache is bypassed when there is a profile, but a new user must still be served from it."""
    monkeypatch.setattr(
        agent_pipeline.cache_service,
        "lookup_cache",
        lambda *_a, **_k: agent_pipeline.cache_service.CachedAnswer(
            answer="Can 2PN tu 3,6 ty dong.", citations=[], verifier_score=0.92
        ),
    )

    result = agent_pipeline._cache_check({"query": "Gia can 2PN?", "memory_profile": ""})

    assert result["used_cache"] is True


def test_personalised_answers_are_never_written_to_the_cache(monkeypatch):
    """Caching a personalised answer would leak it to the next person who asks."""
    stored: list[str] = []
    monkeypatch.setattr(agent_pipeline, "_store_cache", lambda query, *_a, **_k: stored.append(query))
    monkeypatch.setattr(
        agent_pipeline,
        "_get_graph",
        lambda: _FakeGraph({"draft_answer": "Can 3PN tu 5 ty dong.", "verifier_score": 0.95}),
    )

    agent_pipeline.run_pipeline("Gia can 3PN?", memory_profile=PROFILE)
    assert stored == []

    agent_pipeline.run_pipeline("Gia can 3PN?")
    assert stored == ["Gia can 3PN?"]


def test_profile_reaches_the_generate_node(monkeypatch):
    seen: list[str] = []

    def fake_generate(prompt, schema, *_args, **_kwargs):
        seen.append(prompt)
        return schema(text="- Can 3PN tu 5 ty dong.")

    monkeypatch.setattr(agent_pipeline, "generate_json", fake_generate)

    agent_pipeline._generate({"query": "Gia can 3PN?", "memory_profile": PROFILE, "retrieved_docs": []})

    assert "2PN" in seen[0]


def test_customer_memory_recall_never_calls_retrieval_or_a_model(monkeypatch):
    def fail(*_args, **_kwargs):
        raise AssertionError("memory recall must finish before RAG/model calls")

    monkeypatch.setattr(agent_pipeline, "retrieve", fail)
    monkeypatch.setattr(agent_pipeline, "generate_json", fail)
    profile = memory_service.UserProfile(
        unit_types=["2PN+1"],
        budgets=["3.5 - 4 tỷ"],
        projects=["the-pavilion", "the-sapphire"],
    )

    result = agent_pipeline.run_pipeline(
        "Khách của tôi đang quan tâm đến phân khu nào?",
        memory_profile=memory_service.format_profile(profile),
        memory_profile_data=profile,
        session_id=151,
    )

    assert "The Pavilion" in result.draft_answer
    assert "The Sapphire" in result.draft_answer
    assert result.verifier_score == 1.0
    assert result.citations == []


class _FakeGraph:
    """Stands in for the compiled LangGraph so run_pipeline can be driven without LLM calls."""

    def __init__(self, state: dict):
        self._state = state

    def invoke(self, initial):
        return {**initial, **self._state}
