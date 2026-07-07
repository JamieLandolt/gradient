"""Guest what-if calculator: stateless and unauthenticated (FR-3.1.5).

Reuses exactly the same deterministic engine as the authed endpoints; the
assessment structure arrives in the request body and nothing is persisted.
"""

from dataclasses import asdict

from fastapi import APIRouter

from app.core.envelope import success_payload
from app.core.errors import ValidationFailedError
from app.domain.calculation.models import AssessmentItem, InvalidAssessmentStructureError
from app.domain.calculation.required_marks import compute_required_marks
from app.domain.calculation.standing import compute_standing
from app.schemas.api import WhatIfRequest

router = APIRouter(tags=["calculator"])


@router.post("/calculator/what-if")
async def what_if(request: WhatIfRequest) -> dict:
    items = tuple(
        AssessmentItem(
            name=item.name,
            weight=item.weight,
            max_mark=item.max_mark,
            score=item.score,
            hurdle_min_percent=item.hurdle_min_percent,
        )
        for item in request.items
    )
    try:
        standing = compute_standing(items, request.grade_cutoffs)
        result = compute_required_marks(
            items, target_grade=request.target_grade, grade_cutoffs=request.grade_cutoffs
        )
    except InvalidAssessmentStructureError as exc:
        raise ValidationFailedError(str(exc)) from exc

    payload = asdict(result)
    payload["status"] = result.status.value
    payload["standing"] = asdict(standing)
    return success_payload(payload)
