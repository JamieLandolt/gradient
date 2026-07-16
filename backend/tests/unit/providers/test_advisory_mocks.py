"""Determinism and behaviour of the mock recommendation / assistant providers."""

from app.providers.mock.assistant import MockAssistantProvider
from app.providers.mock.recommendations import MockRecommendationProvider

CANDIDATES = [
    {"code": "COMP4702", "title": "Machine Learning",
     "description": "machine learning neural networks", "prereq_status": "not_met"},
    {"code": "COMP3702", "title": "Artificial Intelligence",
     "description": "machine learning agents search", "prereq_status": "met"},
    {"code": "BIOL1020", "title": "Genes, Cells & Evolution",
     "description": "cell genetics evolution", "prereq_status": "met"},
]


class TestRecommendations:
    def test_interest_match_plus_prereq_bonus_ranks_first(self):
        provider = MockRecommendationProvider()

        results = provider.recommend(
            CANDIDATES, ["machine learning"], frozenset(), limit=3
        )

        assert results[0]["course_code"] == "COMP3702"  # matches interest AND prereqs met
        assert results[0]["prereq_status"] == "met"
        assert "prerequisites" in results[0]["reason"]

    def test_completed_courses_are_excluded(self):
        provider = MockRecommendationProvider()

        results = provider.recommend(
            CANDIDATES, ["machine learning"], frozenset({"COMP3702"}), limit=3
        )

        assert all(r["course_code"] != "COMP3702" for r in results)

    def test_deterministic(self):
        provider = MockRecommendationProvider()
        args = (CANDIDATES, ["genetics"], frozenset(), 3)

        assert provider.recommend(*args) == provider.recommend(*args)


class TestAssistantStreaming:
    FACTS = {"GPA": 6.0, "completed courses": 3, "secured percent": 16.0}

    def test_stream_reconstructs_the_full_answer(self):
        provider = MockAssistantProvider()

        full = provider.answer("How am I doing?", self.FACTS)
        streamed = "".join(provider.stream_answer("How am I doing?", self.FACTS))

        assert streamed == full
        assert "GPA" in streamed
        assert "authoritative" in streamed

    def test_stream_yields_multiple_chunks(self):
        provider = MockAssistantProvider()

        chunks = list(provider.stream_answer("hi", self.FACTS))

        assert len(chunks) > 1
