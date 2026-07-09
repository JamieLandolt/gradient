"""Contract tests for the hosted OpenAI-compatible providers.

No network or API key: the HTTP layer is stubbed with httpx.MockTransport, and
the provider classes are driven by a duck-typed fake client. Verifies the shapes
match the mocks and the grounding rules (prereq status never from the model).
"""

import httpx
import pytest

from app.config import Settings
from app.providers.openai_compatible import (
    AIProviderError,
    OpenAICompatibleAssistantProvider,
    OpenAICompatibleClient,
    OpenAICompatibleEmbeddingProvider,
    OpenAICompatibleExtractionProvider,
    OpenAICompatibleRecommendationProvider,
    OpenAICompatibleStudyPlanProvider,
)


class FakeClient:
    def __init__(self, json_reply=None, text_reply="", embedding=None):
        self._json = json_reply or {}
        self._text = text_reply
        self._embedding = embedding if embedding is not None else [0.1] * 8
        self.calls: list[tuple] = []

    def chat_json(self, system, user):
        self.calls.append(("json", system, user))
        return self._json

    def chat_text(self, system, user):
        self.calls.append(("text", system, user))
        return self._text

    def embed(self, text):
        self.calls.append(("embed", text))
        return self._embedding


# ── Extraction ───────────────────────────────────────────────────────────────
def test_extraction_builds_profile_with_prereq_tree():
    reply = {
        "course_code": "comp3506",
        "course_title": "Algorithms & Data Structures",
        "units": 2,
        "description": "Design and analysis of algorithms.",
        "version_label": "2026S2",
        "assessments": [
            {"name": "A1", "weight": 40, "max_mark": 100, "due_date": "2026-09-11"},
            {"name": "Exam", "weight": 60, "hurdle_min_percent": 40, "hurdle_description": "≥40%"},
        ],
        "grade_cutoffs": {"7": 85},
        "prerequisite": "CSSE2002 and (MATH1061 or MATH1071)",
    }
    provider = OpenAICompatibleExtractionProvider(FakeClient(json_reply=reply))

    profile = provider.extract("<ecp text>")

    assert profile.course_code == "COMP3506"
    assert len(profile.assessments) == 2
    assert profile.prerequisite_tree.node_type == "and"
    assert profile.grade_cutoffs == {7: 85.0}
    assert profile.warnings == ()


def test_extraction_warns_when_weights_do_not_sum_to_100():
    reply = {
        "course_code": "COMP3506",
        "course_title": "x",
        "assessments": [{"name": "A1", "weight": 40}, {"name": "A2", "weight": 40}],
    }
    profile = OpenAICompatibleExtractionProvider(FakeClient(json_reply=reply)).extract("t")

    assert any("sum to" in w for w in profile.warnings)


def test_extraction_rejects_invalid_course_code():
    reply = {"course_code": "NOTACODE", "course_title": "x"}
    with pytest.raises(ValueError):
        OpenAICompatibleExtractionProvider(FakeClient(json_reply=reply)).extract("t")


def test_extraction_keeps_unparseable_prereq_as_note():
    reply = {
        "course_code": "COMP3506",
        "course_title": "x",
        "assessments": [{"name": "All", "weight": 100}],
        "prerequisite": "permission of the head of school",
    }
    profile = OpenAICompatibleExtractionProvider(FakeClient(json_reply=reply)).extract("t")

    assert profile.prerequisite_tree.node_type == "note"
    assert any("manual check" in w for w in profile.warnings)


# ── Recommendations ──────────────────────────────────────────────────────────
def test_recommendation_prereq_status_comes_from_candidate_not_model():
    candidates = [{"code": "INFS2200", "title": "DB", "description": "", "prereq_status": "met"}]
    reply = {"recommendations": [
        {"course_code": "INFS2200", "reason": "matches databases", "score": 9,
         "prereq_status": "not_met"}
    ]}
    provider = OpenAICompatibleRecommendationProvider(FakeClient(json_reply=reply))

    items = provider.recommend(candidates, ["databases"], frozenset(), 5)

    assert items[0]["prereq_status"] == "met"  # deterministic wins over the model's value
    assert items[0]["rank"] == 1


def test_recommendation_drops_hallucinated_codes():
    candidates = [{"code": "INFS2200", "title": "DB", "prereq_status": "met"}]
    reply = {"recommendations": [{"course_code": "GHOST9999", "reason": "x", "score": 9}]}
    provider = OpenAICompatibleRecommendationProvider(FakeClient(json_reply=reply))

    assert provider.recommend(candidates, [], frozenset(), 5) == []


# ── Study plans ──────────────────────────────────────────────────────────────
def test_study_plan_shapes_sessions_with_sort_order():
    reply = {"sessions": [
        {"session_date": "2026-09-01", "duration_minutes": 90, "focus": "A1 revision",
         "assessment_name": "A1"},
    ]}
    provider = OpenAICompatibleStudyPlanProvider(FakeClient(json_reply=reply))

    sessions = provider.generate(
        "COMP3506",
        [{"name": "A1", "weight": 40, "due_date": "2026-09-11", "score": None}],
        target_grade=6,
        required_average_percent=73.8,
        start_date="2026-08-20",
    )

    assert sessions[0]["sort_order"] == 0
    assert sessions[0]["duration_minutes"] == 90
    assert sessions[0]["assessment_name"] == "A1"


# ── Assistant ────────────────────────────────────────────────────────────────
def test_assistant_grounds_on_facts_and_returns_text():
    client = FakeClient(text_reply="You need about 74% on the final.")
    provider = OpenAICompatibleAssistantProvider(client)

    answer = provider.answer("What do I need?", {"GPA": 6.0, "secured percent": 16.0})

    assert answer == "You need about 74% on the final."
    _, _system, user = client.calls[0]
    assert "GPA: 6.0" in user and "secured percent: 16.0" in user


# ── Embeddings ───────────────────────────────────────────────────────────────
def test_embedding_provider_returns_vector_and_model_name():
    provider = OpenAICompatibleEmbeddingProvider(
        FakeClient(embedding=[0.1, 0.2, 0.3]), "text-embedding-v3"
    )

    assert provider.model_name == "text-embedding-v3"
    assert provider.embed("machine learning") == [0.1, 0.2, 0.3]


# ── HTTP client (httpx.MockTransport) ────────────────────────────────────────
def _client_with(handler) -> OpenAICompatibleClient:
    settings = Settings(
        AI_PROVIDER="openai_compatible", DASHSCOPE_API_KEY="test-key", _env_file=None
    )
    client = OpenAICompatibleClient(settings)
    client._http = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url=settings.ai_base_url.rstrip("/"),
        timeout=5,
    )
    return client


def test_client_chat_json_parses_message_content():
    def handler(_request):
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"a": 1}'}}]})

    assert _client_with(handler).chat_json("s", "u") == {"a": 1}


def test_client_raises_when_content_is_not_json():
    def handler(_request):
        return httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]})

    with pytest.raises(AIProviderError):
        _client_with(handler).chat_json("s", "u")


def test_client_retries_then_raises_on_http_error():
    calls = {"n": 0}

    def handler(_request):
        calls["n"] += 1
        return httpx.Response(500)

    with pytest.raises(AIProviderError):
        _client_with(handler).chat_json("s", "u")
    assert calls["n"] == 2  # ai_max_retries default 1 → 2 attempts


def test_client_embed_returns_vector():
    def handler(_request):
        return httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2]}]})

    assert _client_with(handler).embed("x") == [0.1, 0.2]


# ── Streaming assistant (SSE) ────────────────────────────────────────────────
def test_client_chat_text_stream_parses_sse_tokens():
    sse = (
        'data: {"choices":[{"delta":{"content":"You "}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"need "}}]}\n\n'
        ': keep-alive comment line\n\n'
        'data: {"choices":[{"delta":{"content":"74%."}}]}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(_request):
        return httpx.Response(200, content=sse.encode())

    tokens = list(_client_with(handler).chat_text_stream("s", "u"))

    assert "".join(tokens) == "You need 74%."


def test_client_chat_text_stream_raises_on_http_error():
    def handler(_request):
        return httpx.Response(500)

    with pytest.raises(AIProviderError):
        list(_client_with(handler).chat_text_stream("s", "u"))


def test_assistant_stream_answer_uses_grounded_facts():
    captured = {}

    class StreamingFakeClient:
        def chat_text_stream(self, system, user):
            captured["user"] = user
            return iter(["You ", "need ", "74%."])

    provider = OpenAICompatibleAssistantProvider(StreamingFakeClient())

    tokens = list(provider.stream_answer("What do I need?", {"GPA": 6.0}))

    assert "".join(tokens) == "You need 74%."
    assert "GPA: 6.0" in captured["user"]
