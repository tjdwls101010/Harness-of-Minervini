from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from scripts.modules.market_clock import last_completed_session


@dataclass(frozen=True)
class AnalysisClock:
    """The completed-session boundary that every point-in-time provider receives."""

    date: date
    mode: str
    timezone: str = "America/New_York"
    completed_session: bool = True


def _parse_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise ValueError("as_of must use YYYY-MM-DD") from error


def resolve_as_of(value: str | date | None = None, *, now: datetime | None = None) -> AnalysisClock:
    """Resolve an explicit completed-session boundary or the latest completed session."""

    latest_completed = last_completed_session(now)
    if value is None:
        return AnalysisClock(date=latest_completed, mode="last_completed_session")

    explicit = _parse_date(value)
    if explicit > latest_completed:
        raise ValueError("as_of cannot be after the last completed US regular session")
    return AnalysisClock(date=explicit, mode="explicit")
