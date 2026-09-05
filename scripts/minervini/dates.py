"""Optional ISO dates and explicit request refusals."""

from __future__ import annotations

from datetime import date
from typing import Any

from .contracts import RequestError


def parse_iso(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError, OverflowError):
        return None


def request_date(value: Any, field: str) -> date:
    """A calendar date the caller wrote as ``YYYY-MM-DD``, or a refusal naming the field.

    The extended form only. ``date.fromisoformat`` also reads the basic form and a full
    timestamp, and the reducer's own reader takes neither -- so a request written either way
    parses here, is written back in a shape the reducer answers "missing" to, and the two
    halves of the harness disagree about whether the field was supplied at all. A number is
    refused for the same reason: ``20251201`` is not a date the reducer can read.
    """

    if not isinstance(value, str) or len(value) != 10 or value[4] != "-" or value[7] != "-":
        raise RequestError(f"{field} must be an ISO date written YYYY-MM-DD", field)
    result = parse_iso(value)
    if result is None:
        raise RequestError(f"{field} must be an ISO date written YYYY-MM-DD", field)
    return result
