"""In-memory doubles for the repositories, mirroring their public interfaces."""

from typing import Any

from fastapi.testclient import TestClient

from app.api import deps
from app.config import Settings
from app.core.auth import AuthUser, get_current_user
from app.domain.planning.models import PlannableCourse, PrereqNode
from app.main import create_app
from app.providers.factory import get_providers
from app.services.advisory import AdvisoryService
from app.services.ingestion import IngestionService
from app.services.planner import PlannerService
from app.services.tracking import TrackingService

CSSE1001_ASSESSMENTS = [
    {"id": 1, "name": "Assignment 1", "weight": 20, "max_mark": 100, "due_date": "2026-03-27",
     "hurdle_min_percent": None, "hurdle_description": None, "sort_order": 0},
    {"id": 2, "name": "Assignment 2", "weight": 30, "max_mark": 100, "due_date": "2026-05-15",
     "hurdle_min_percent": None, "hurdle_description": None, "sort_order": 1},
    {"id": 3, "name": "Final Exam", "weight": 50, "max_mark": 100, "due_date": "2026-06-12",
     "hurdle_min_percent": 40, "hurdle_description": "Must score at least 40% on the final exam.",
     "sort_order": 2},
]


class FakeCatalogueRepository:
    def __init__(self):
        self.courses = {
            "CSSE1001": {"id": 1, "code": "CSSE1001", "title": "Intro to Software Engineering",
                         "units": 2, "description": "Python programming"},
            "MATH1051": {"id": 2, "code": "MATH1051", "title": "Calculus & Linear Algebra I",
                         "units": 2, "description": "Calculus"},
            "COMP3506": {"id": 3, "code": "COMP3506", "title": "Algorithms & Data Structures",
                         "units": 2, "description": "Algorithms"},
        }
        self.offerings = [
            {"id": 10, "course_id": 1, "year": 2026, "semester": "S1"},
            {"id": 11, "course_id": 1, "year": 2026, "semester": "S2"},
            {"id": 12, "course_id": 2, "year": 2026, "semester": "S1"},
            {"id": 13, "course_id": 3, "year": 2026, "semester": "S2"},
        ]
        self.profiles = {
            1: {"id": 100, "version_label": "2026S1", "status": "verified",
                "extracted_at": "2026-01-01T00:00:00Z", "extraction_provider": "seed",
                "assessments": CSSE1001_ASSESSMENTS, "grade_cutoffs": None},
        }
        self.prereq_trees = {
            3: PrereqNode.course("CSSE1001"),
        }
        self.raw_prereqs = {3: "CSSE1001"}
        self.programs = [
            {"id": 1, "code": "BCompSc", "title": "Bachelor of Computer Science",
             "total_units": 32, "is_sample": True},
        ]
        self.program_courses = {
            1: [
                {"requirement_kind": "required", "courses": {"code": "CSSE1001"}},
                {"requirement_kind": "required", "courses": {"code": "MATH1051"}},
                {"requirement_kind": "required", "courses": {"code": "COMP3506"}},
            ],
        }
        self._next_offering_id = 100

    def list_courses(self):
        return [dict(c) for c in self.courses.values()]

    def get_course(self, code: str):
        course = self.courses.get(code)
        return dict(course) if course else None

    def get_offering_periods(self, course_id: int):
        return frozenset(o["semester"] for o in self.offerings if o["course_id"] == course_id)

    def find_offering(self, course_id: int, year: int, semester: str):
        for o in self.offerings:
            if (o["course_id"], o["year"], o["semester"]) == (course_id, year, semester):
                return dict(o)
        return None

    def create_offering(self, course_id: int, year: int, semester: str):
        self._next_offering_id += 1
        offering = {"id": self._next_offering_id, "course_id": course_id,
                    "year": year, "semester": semester}
        self.offerings.append(offering)
        return dict(offering)

    def get_verified_profile(self, course_id: int):
        profile = self.profiles.get(course_id)
        return dict(profile) if profile else None

    def get_prereq_tree(self, course_id: int):
        return self.prereq_trees.get(course_id)

    def get_prereq_raw_text(self, course_id: int):
        return self.raw_prereqs.get(course_id)

    def list_programs(self):
        return [dict(p) for p in self.programs]

    def get_program_courses(self, program_id: int):
        return list(self.program_courses.get(program_id, []))

    def get_plannable_courses(self, codes: list[str]):
        result = []
        for code in codes:
            course = self.courses.get(code)
            if course:
                result.append(
                    PlannableCourse(
                        code=code,
                        units=float(course["units"]),
                        offerings=self.get_offering_periods(course["id"]),
                        prereq=self.prereq_trees.get(course["id"]),
                    )
                )
        return result


class FakeStudentRepository:
    def __init__(self, catalogue: FakeCatalogueRepository):
        self._catalogue = catalogue
        self.enrolments: list[dict[str, Any]] = []
        self.grades: list[dict[str, Any]] = []
        self.custom_assessments: list[dict[str, Any]] = []
        self.user_programs: list[dict[str, Any]] = []
        self.profiles: dict[str, dict[str, Any]] = {}
        self.deleted_accounts: list[str] = []
        self._next_id = 0

    def _new_id(self) -> int:
        self._next_id += 1
        return self._next_id

    def _hydrate(self, enrolment: dict[str, Any]) -> dict[str, Any]:
        offering = next(
            o for o in self._catalogue.offerings
            if o["id"] == enrolment["course_offering_id"]
        )
        course = next(
            dict(c) for c in self._catalogue.courses.values()
            if c["id"] == offering["course_id"]
        )
        return {
            **{k: v for k, v in enrolment.items() if k != "course_offering_id"},
            "course_offerings": {**offering, "courses": course},
        }

    def list_enrolments(self, user_id: str):
        return [self._hydrate(e) for e in self.enrolments if e["user_id"] == user_id]

    def get_enrolment(self, user_id: str, enrolment_id: int):
        for e in self.enrolments:
            if e["user_id"] == user_id and e["id"] == enrolment_id:
                return self._hydrate(e)
        return None

    def create_enrolment(self, user_id: str, values: dict[str, Any]):
        row = {**values, "user_id": user_id, "id": self._new_id()}
        row.setdefault("final_grade", None)
        row.setdefault("final_percent", None)
        row.setdefault("is_transfer", False)
        self.enrolments.append(row)
        return dict(row)

    def update_enrolment(self, user_id: str, enrolment_id: int, values: dict[str, Any]):
        for e in self.enrolments:
            if e["user_id"] == user_id and e["id"] == enrolment_id:
                e.update(values)
                return dict(e)
        return None

    def delete_enrolment(self, user_id: str, enrolment_id: int) -> bool:
        before = len(self.enrolments)
        self.enrolments = [
            e for e in self.enrolments
            if not (e["user_id"] == user_id and e["id"] == enrolment_id)
        ]
        return len(self.enrolments) < before

    def completed_course_codes(self, user_id: str):
        return frozenset(
            self._hydrate(e)["course_offerings"]["courses"]["code"]
            for e in self.enrolments
            if e["user_id"] == user_id and e["status"] == "completed"
        )

    def list_custom_assessments(self, user_id: str, enrolment_id: int):
        return [
            dict(a) for a in self.custom_assessments
            if a["user_id"] == user_id and a["enrolment_id"] == enrolment_id
        ]

    def create_custom_assessment(self, user_id: str, enrolment_id: int, values):
        row = {**values, "user_id": user_id, "enrolment_id": enrolment_id, "id": self._new_id()}
        self.custom_assessments.append(row)
        return dict(row)

    def update_custom_assessment(self, user_id: str, assessment_id: int, values):
        for a in self.custom_assessments:
            if a["user_id"] == user_id and a["id"] == assessment_id:
                a.update(values)
                return dict(a)
        return None

    def delete_custom_assessment(self, user_id: str, assessment_id: int) -> bool:
        before = len(self.custom_assessments)
        self.custom_assessments = [
            a for a in self.custom_assessments
            if not (a["user_id"] == user_id and a["id"] == assessment_id)
        ]
        return len(self.custom_assessments) < before

    def list_grades(self, user_id: str, enrolment_id: int):
        return [
            dict(g) for g in self.grades
            if g["user_id"] == user_id and g["enrolment_id"] == enrolment_id
        ]

    def upsert_grade(self, user_id, enrolment_id, score,
                     assessment_id=None, custom_assessment_id=None):
        for g in self.grades:
            if (
                g["enrolment_id"] == enrolment_id
                and g["assessment_id"] == assessment_id
                and g["custom_assessment_id"] == custom_assessment_id
            ):
                g["score"] = score
                return dict(g)
        row = {
            "id": self._new_id(), "user_id": user_id, "enrolment_id": enrolment_id,
            "assessment_id": assessment_id, "custom_assessment_id": custom_assessment_id,
            "score": score,
        }
        self.grades.append(row)
        return dict(row)

    def delete_grade(self, user_id: str, grade_id: int) -> bool:
        before = len(self.grades)
        self.grades = [
            g for g in self.grades
            if not (g["user_id"] == user_id and g["id"] == grade_id)
        ]
        return len(self.grades) < before

    def get_user_programs(self, user_id: str):
        links = sorted(
            (link for link in self.user_programs if link["user_id"] == user_id),
            key=lambda link: link["position"],
        )
        return [
            {"position": link["position"],
             "programs": next(dict(p) for p in self._catalogue.programs
                              if p["id"] == link["program_id"])}
            for link in links
        ]

    def set_user_programs(self, user_id: str, program_ids: list[int]):
        self.user_programs = [
            link for link in self.user_programs if link["user_id"] != user_id
        ]
        for index, program_id in enumerate(program_ids[:2]):
            self.user_programs.append(
                {"user_id": user_id, "program_id": program_id, "position": index + 1}
            )

    def get_profile(self, user_id: str):
        profile = self.profiles.get(user_id)
        return dict(profile) if profile else None

    def update_profile(self, user_id: str, values: dict[str, Any]):
        if user_id not in self.profiles:
            return None
        self.profiles[user_id].update(values)
        return dict(self.profiles[user_id])

    def delete_account(self, user_id: str) -> None:
        self.deleted_accounts.append(user_id)


class FakeIngestionRepository:
    """In-memory mirror of IngestionRepository, sharing the fake catalogue."""

    def __init__(self, catalogue: FakeCatalogueRepository):
        self._catalogue = catalogue
        self.jobs: list[dict[str, Any]] = []
        self.versions: list[dict[str, Any]] = []
        self.embeddings: dict[int, list[float]] = {}
        self.prereq_raw: dict[int, str] = {}
        self._next_id = 1000

    def _new_id(self) -> int:
        self._next_id += 1
        return self._next_id

    def create_course_if_missing(self, extracted):
        existing = self._catalogue.courses.get(extracted.course_code)
        if existing:
            return dict(existing)
        course = {
            "id": self._new_id(), "code": extracted.course_code,
            "title": extracted.course_title, "units": extracted.units,
            "description": extracted.description,
        }
        self._catalogue.courses[extracted.course_code] = course
        return dict(course)

    def find_profile_version(self, course_id, version_label):
        for v in self.versions:
            if v["course_id"] == course_id and v["version_label"] == version_label:
                return dict(v)
        return None

    def create_draft_version(self, course_id, extracted, source_type, source_ref,
                             provider_name):
        version = {
            "id": self._new_id(), "course_id": course_id,
            "version_label": extracted.version_label, "status": "draft",
            "source_type": source_type, "source_ref": source_ref,
            "extraction_provider": provider_name,
            "assessments": [
                {"id": self._new_id(), "name": a.name, "weight": a.weight,
                 "max_mark": a.max_mark, "due_date": a.due_date,
                 "hurdle_min_percent": a.hurdle_min_percent,
                 "hurdle_description": a.hurdle_description, "sort_order": i}
                for i, a in enumerate(extracted.assessments)
            ],
            "grade_cutoffs": extracted.grade_cutoffs,
        }
        self.versions.append(version)
        return dict(version)

    def get_version(self, version_id):
        for v in self.versions:
            if v["id"] == version_id:
                return dict(v)
        return None

    def list_versions(self, status):
        return [dict(v) for v in self.versions if v["status"] == status]

    def set_version_status(self, version_id, status, verified_by):
        for v in self.versions:
            if v["id"] == version_id:
                v["status"] = status
                v["verified_by"] = verified_by
                if status == "verified":
                    # Also expose to the catalogue fake so projections use it.
                    self._catalogue.profiles[v["course_id"]] = dict(v)
                return dict(v)
        return None

    def replace_prereq_tree(self, course_id, raw_text, tree):
        self.prereq_raw[course_id] = raw_text
        if tree is not None:
            self._catalogue.prereq_trees[course_id] = tree
            self._catalogue.raw_prereqs[course_id] = raw_text

    def create_job(self, user_id, values):
        job = {**values, "id": self._new_id(), "submitted_by": user_id,
               "profile_version_id": None, "error": ""}
        self.jobs.append(job)
        return dict(job)

    def update_job(self, job_id, values):
        for job in self.jobs:
            if job["id"] == job_id:
                job.update(values)
                return dict(job)
        return None

    def get_job(self, user_id, job_id):
        for job in self.jobs:
            if job["id"] == job_id and job["submitted_by"] == user_id:
                return dict(job)
        return None

    def upsert_embedding(self, course_id, embedding, model):
        self.embeddings[course_id] = embedding

    def match_courses(self, embedding, limit):
        def cosine(a, b):
            return sum(x * y for x, y in zip(a, b, strict=True))

        scored = []
        for course in self._catalogue.courses.values():
            stored = self.embeddings.get(course["id"])
            if stored is None:
                continue
            scored.append(
                {"course_id": course["id"], "code": course["code"],
                 "title": course["title"], "description": course["description"],
                 "similarity": cosine(embedding, stored)}
            )
        scored.sort(key=lambda row: -row["similarity"])
        return scored[:limit]


def build_client(
    catalogue: FakeCatalogueRepository | None = None,
    students: FakeStudentRepository | None = None,
    user: AuthUser | None = None,
    ingestion: FakeIngestionRepository | None = None,
) -> tuple[TestClient, FakeCatalogueRepository, FakeStudentRepository]:
    catalogue = catalogue or FakeCatalogueRepository()
    students = students or FakeStudentRepository(catalogue)
    ingestion = ingestion or FakeIngestionRepository(catalogue)
    settings = Settings(_env_file=None)
    providers = get_providers(settings)
    tracking = TrackingService(catalogue, students)
    app = create_app(settings)
    app.dependency_overrides[deps.get_catalogue_repo] = lambda: catalogue
    app.dependency_overrides[deps.get_student_repo] = lambda: students
    app.dependency_overrides[deps.get_tracking_service] = lambda: tracking
    app.dependency_overrides[deps.get_planner_service] = lambda: PlannerService(
        catalogue, students
    )
    app.dependency_overrides[deps.get_ingestion_repo] = lambda: ingestion
    app.dependency_overrides[deps.get_ingestion_service] = lambda: IngestionService(
        ingestion, providers
    )
    app.dependency_overrides[deps.get_advisory_service] = lambda: AdvisoryService(
        catalogue, students, ingestion, tracking, providers
    )
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    client = TestClient(app, raise_server_exceptions=False)
    return client, catalogue, students
