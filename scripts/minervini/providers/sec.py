from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable, Mapping


def _filed_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def select_filed_as_of(records: Iterable[Mapping[str, Any]], as_of: str | date) -> dict[str, Any] | None:
    """Return the latest fact filed on or before the audit boundary, never a future filing."""

    boundary = _filed_date(as_of)
    eligible: list[tuple[date, Mapping[str, Any]]] = []
    for record in records:
        filed_at = record.get("filed_at")
        if filed_at is None:
            continue
        filed = _filed_date(filed_at)
        if filed <= boundary:
            eligible.append((filed, record))
    if not eligible:
        return None
    return dict(max(eligible, key=lambda item: item[0])[1])
