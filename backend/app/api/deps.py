"""Dependency wiring: settings → Supabase client → repositories → services.

Tests override these provider functions with fakes via app.dependency_overrides.
"""

from fastapi import Depends, Request

from app.config import Settings
from app.core.db import get_supabase_client
from app.repositories.catalogue import CatalogueRepository
from app.repositories.students import StudentRepository
from app.services.planner import PlannerService
from app.services.tracking import TrackingService


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_catalogue_repo(settings: Settings = Depends(get_settings_dep)) -> CatalogueRepository:
    return CatalogueRepository(get_supabase_client(settings))


def get_student_repo(settings: Settings = Depends(get_settings_dep)) -> StudentRepository:
    return StudentRepository(get_supabase_client(settings))


def get_tracking_service(
    catalogue: CatalogueRepository = Depends(get_catalogue_repo),
    students: StudentRepository = Depends(get_student_repo),
) -> TrackingService:
    return TrackingService(catalogue, students)


def get_planner_service(
    catalogue: CatalogueRepository = Depends(get_catalogue_repo),
    students: StudentRepository = Depends(get_student_repo),
) -> PlannerService:
    return PlannerService(catalogue, students)
