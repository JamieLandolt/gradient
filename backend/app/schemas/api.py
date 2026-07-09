"""Request/response models for the v1 API (server-side validation, NFR-5.3.5)."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

Semester = Literal["S1", "S2", "SUMMER"]
EnrolmentStatus = Literal["planned", "in_progress", "completed"]


# ── Requests ─────────────────────────────────────────────────────────────────
class EnrolmentCreateRequest(BaseModel):
    course_code: str = Field(min_length=1, max_length=20)
    year: int = Field(ge=2000, le=2100)
    semester: Semester
    status: EnrolmentStatus = "in_progress"
    is_transfer: bool = False
    final_grade: int | None = Field(default=None, ge=1, le=7)
    final_percent: float | None = Field(default=None, ge=0, le=100)


class EnrolmentUpdateRequest(BaseModel):
    status: EnrolmentStatus | None = None
    final_grade: int | None = Field(default=None, ge=1, le=7)
    final_percent: float | None = Field(default=None, ge=0, le=100)


class CustomAssessmentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    weight: float = Field(ge=0, le=100)
    max_mark: float = Field(default=100, gt=0)
    due_date: date | None = None
    hurdle_min_percent: float | None = Field(default=None, ge=0, le=100)
    hurdle_description: str | None = None


class GradeUpsertRequest(BaseModel):
    assessment_id: int | None = None
    custom_assessment_id: int | None = None
    score: float = Field(ge=0)

    def target_is_valid(self) -> bool:
        return (self.assessment_id is None) != (self.custom_assessment_id is None)


class RequiredMarksRequest(BaseModel):
    target_grade: int = Field(default=4, ge=1, le=7)
    what_if_scores: dict[str, float] = Field(default_factory=dict)


class WhatIfItem(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    weight: float = Field(ge=0, le=100)
    max_mark: float = Field(default=100, gt=0)
    score: float | None = Field(default=None, ge=0)
    hurdle_min_percent: float | None = Field(default=None, ge=0, le=100)


class WhatIfRequest(BaseModel):
    """Guest calculator: full structure in the request, nothing persisted (FR-3.1.5)."""

    items: list[WhatIfItem] = Field(min_length=1, max_length=50)
    target_grade: int = Field(default=4, ge=1, le=7)
    grade_cutoffs: dict[int, float] | None = None


class SequenceRequest(BaseModel):
    start_year: int = Field(ge=2000, le=2100)
    start_semester: Literal["S1", "S2"]
    max_units_per_semester: float = Field(default=8, gt=0, le=20)
    # Planner preferences (FR-3.6.6, optional): front-load courses that are
    # immediately takeable, and/or courses matching topic interests. Both only
    # re-order the deterministic plan; they never relax prerequisite correctness.
    prioritise_available: bool = False
    interests: list[str] = Field(default_factory=list, max_length=20)


class DegreePlanSaveRequest(SequenceRequest):
    """Generate a sequence with the same inputs as /planner/sequence and save it
    under a name (FR-3.6.2)."""

    name: str = Field(default="My plan", min_length=1, max_length=100)


class ProgramSelectionRequest(BaseModel):
    program_ids: list[int] = Field(min_length=1, max_length=2)


class ProfileUpdateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)


class IngestionSubmitRequest(BaseModel):
    source_type: Literal["text", "url", "upload"] = "text"
    payload: str = Field(min_length=1, max_length=100_000)
    source_ref: str = Field(default="", max_length=500)


class RecommendRequest(BaseModel):
    interests: list[str] = Field(default_factory=list, max_length=20)
    limit: int = Field(default=5, ge=1, le=20)


class StudyPlanGenerateRequest(BaseModel):
    enrolment_id: int
    target_grade: int = Field(default=4, ge=1, le=7)
    start_date: date | None = None


class AssistantAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    enrolment_id: int | None = None


# ── Responses (subset — routers return dicts shaped like these) ─────────────
class AssessmentItemResponse(BaseModel):
    id: int
    source: Literal["profile", "custom"]
    name: str
    weight: float
    max_mark: float
    due_date: date | None
    hurdle_min_percent: float | None
    hurdle_description: str | None
    score: float | None
