"""Consistent API response envelope: {success, data, error, meta}."""

from typing import Any

from fastapi.responses import JSONResponse


def success_payload(data: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"success": True, "data": data, "error": None, "meta": meta}


def error_payload(message: str, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"success": False, "data": None, "error": message, "meta": meta}


def error_response(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=error_payload(message))
