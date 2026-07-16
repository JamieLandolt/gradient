"""Dependency wiring: settings → Supabase client → repositories → services.

Tests override these provider functions with fakes via app.dependency_overrides.
"""

from fastapi import Depends, Request

from app.config import Settings
from app.core.auth import AuthUser, get_current_user
from app.core.db import get_supabase_client
from app.core.errors import ForbiddenError
from app.providers.factory import ProviderBundle, get_providers
from app.repositories.artifacts import ArtifactRepository
from app.repositories.catalogue import CatalogueRepository
from app.repositories.ingestion import IngestionRepository
from app.repositories.students import StudentRepository
from app.services.advisory import AdvisoryService
from app.services.ingestion import IngestionService
from app.services.planner import PlannerService
from app.services.study_plan import WeeklyStudyPlanService
from app.services.tracking import TrackingService


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_catalogue_repo(settings: Settings = Depends(get_settings_dep)) -> CatalogueRepository:
    return CatalogueRepository(get_supabase_client(settings))


def get_student_repo(settings: Settings = Depends(get_settings_dep)) -> StudentRepository:
    return StudentRepository(get_supabase_client(settings))


def get_artifact_repo(settings: Settings = Depends(get_settings_dep)) -> ArtifactRepository:
    return ArtifactRepository(get_supabase_client(settings))


def get_tracking_service(
    catalogue: CatalogueRepository = Depends(get_catalogue_repo),
    students: StudentRepository = Depends(get_student_repo),
) -> TrackingService:
    return TrackingService(catalogue, students)


def get_planner_service(
    catalogue: CatalogueRepository = Depends(get_catalogue_repo),
    students: StudentRepository = Depends(get_student_repo),
    artifacts: ArtifactRepository = Depends(get_artifact_repo),
) -> PlannerService:
    return PlannerService(catalogue, students, artifacts)


def get_ingestion_repo(settings: Settings = Depends(get_settings_dep)) -> IngestionRepository:
    return IngestionRepository(get_supabase_client(settings))


def get_providers_dep(settings: Settings = Depends(get_settings_dep)) -> ProviderBundle:
    return get_providers(settings)


def get_ingestion_service(
    repo: IngestionRepository = Depends(get_ingestion_repo),
    providers: ProviderBundle = Depends(get_providers_dep),
) -> IngestionService:
    return IngestionService(repo, providers)


def get_weekly_study_plan_service(
    students: StudentRepository = Depends(get_student_repo),
    tracking: TrackingService = Depends(get_tracking_service),
    artifacts: ArtifactRepository = Depends(get_artifact_repo),
) -> WeeklyStudyPlanService:
    return WeeklyStudyPlanService(students, tracking, artifacts)


def get_advisory_service(
    catalogue: CatalogueRepository = Depends(get_catalogue_repo),
    students: StudentRepository = Depends(get_student_repo),
    ingestion: IngestionRepository = Depends(get_ingestion_repo),
    tracking: TrackingService = Depends(get_tracking_service),
    providers: ProviderBundle = Depends(get_providers_dep),
    artifacts: ArtifactRepository = Depends(get_artifact_repo),
) -> AdvisoryService:
    return AdvisoryService(catalogue, students, ingestion, tracking, providers, artifacts)


def get_current_curator(
    user: AuthUser = Depends(get_current_user),
    students: StudentRepository = Depends(get_student_repo),
) -> AuthUser:
    """Curator/admin gate for ECP review endpoints (FR-3.5.3)."""
    profile = students.get_profile(user.id)
    if profile is None or profile.get("role") not in ("curator", "admin"):
        raise ForbiddenError("Curator access required")
    return user
