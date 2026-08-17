from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from . import SCHEMA_VERSION


VALID_STATUSES = {"ok", "partial", "unavailable", "needs_input"}


@dataclass(frozen=True)
class RequestError(Exception):
    message: str
    field: str
    code: str = "invalid_request"
    retryable: bool = False


def as_of_block(value: str | None = None) -> dict[str, Any]:
    return {
        "mode": "explicit" if value else "last_completed_session",
        "date": value or date.today().isoformat(),
        "timezone": "America/New_York",
        "completed_session": True,
    }


def envelope(
    operation: str,
    *,
    request: dict[str, Any] | None = None,
    as_of: dict[str, Any] | None = None,
    status: str = "ok",
    data: Any = None,
    signals: list[dict[str, Any]] | None = None,
    missing: list[dict[str, Any]] | None = None,
    sources: list[dict[str, Any]] | None = None,
    doctrine_ids: list[str] | None = None,
    next_capabilities: list[str] | None = None,
    side_effects: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if status not in VALID_STATUSES:
        raise ValueError(f"unsupported status: {status}")
    return {
        "schema_version": SCHEMA_VERSION,
        "operation": operation,
        "request": request or {},
        "as_of": as_of or as_of_block(),
        "status": status,
        "data": {} if data is None else data,
        "signals": signals or [],
        "missing": missing or [],
        "sources": sources or [],
        "doctrine_ids": doctrine_ids or [],
        "next_capabilities": next_capabilities or [],
        "side_effects": side_effects or [],
    }


def error_envelope(operation: str, error: RequestError) -> dict[str, Any]:
    return envelope(
        operation,
        request={error.field: None},
        status="needs_input",
        data={
            "error": {
                "code": error.code,
                "message": error.message,
                "field": error.field,
                "retryable": error.retryable,
            }
        },
    )
