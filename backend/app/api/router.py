"""Aggregates all /api/v1 routers."""

from fastapi import APIRouter

from app.api import account, calculator, catalogue, enrolments, health, planner

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(catalogue.router)
api_router.include_router(enrolments.router)
api_router.include_router(calculator.router)
api_router.include_router(planner.router)
api_router.include_router(account.router)
