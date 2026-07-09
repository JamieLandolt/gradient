"""Determinism and behaviour of the mock recommendation / study-plan providers."""

from app.providers.mock.assistant import MockAssistantProvider
from app.providers.mock.recommendations import MockRecommendationProvider
from app.providers.mock.study_plans import MockStudyPlanProvider

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


class TestStudyPlans:
    ITEMS = [
        {"name": "Assignment 2", "weight": 30, "due_date": "2026-05-15", "score": None},
        {"name": "Final Exam", "weight": 50, "due_date": "2026-06-12", "score": None},
        {"name": "Assignment 1", "weight": 20, "due_date": "2026-03-27", "score": 80},
    ]

    def test_sessions_only_for_remaining_items_before_due_dates(self):
        provider = MockStudyPlanProvider()

        sessions = provider.generate("CSSE1001", self.ITEMS, 5, 55.0, "2026-04-01")

        names = {s["assessment_name"] for s in sessions}
        assert names == {"Assignment 2", "Final Exam"}
        for session in sessions:
            due = next(i["due_date"] for i in self.ITEMS
                       if i["name"] == session["assessment_name"])
            assert session["session_date"] <= due

    def test_heavier_items_get_more_sessions(self):
        provider = MockStudyPlanProvider()

        sessions = provider.generate("CSSE1001", self.ITEMS, 5, 55.0, "2026-04-01")

        exam_count = sum(1 for s in sessions if s["assessment_name"] == "Final Exam")
        assignment_count = sum(
            1 for s in sessions if s["assessment_name"] == "Assignment 2"
        )
        assert exam_count > assignment_count

    def test_deterministic(self):
        provider = MockStudyPlanProvider()

        first = provider.generate("CSSE1001", self.ITEMS, 5, 55.0, "2026-04-01")
        second = provider.generate("CSSE1001", self.ITEMS, 5, 55.0, "2026-04-01")

        assert first == second


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
