from __future__ import annotations

from datetime import date, datetime, timezone
from hashlib import sha256
from typing import Callable

from ..clock import ET, last_completed_session
from . import ProviderSnapshot, ProviderUnavailable, SnapshotMeta, fetch_with_one_retry


def raw_snapshot(
    *,
    fetch: Callable[[], str],
    as_of: str | date | None = None,
    retrieved_at: datetime | None = None,
) -> ProviderSnapshot[str]:
    """Preserve raw current Finviz evidence and refuse a false historical snapshot."""

    observed_at = retrieved_at or datetime.now(timezone.utc)
    observed_session_date = observed_at.astimezone(ET).date()
    requested_date = date.fromisoformat(str(as_of)) if as_of is not None else observed_session_date
    if as_of is not None and (
        requested_date != observed_session_date or last_completed_session(observed_at) != requested_date
    ):
        raise ProviderUnavailable("finviz", "historical_snapshot_unavailable", operation="raw_snapshot")
    document = fetch_with_one_retry("finviz", "raw_snapshot", fetch)
    if not isinstance(document, str):
        raise ProviderUnavailable("finviz", "invalid_raw_snapshot", operation="raw_snapshot")
    return ProviderSnapshot(
        data=document,
        meta=SnapshotMeta(
            provider="finviz",
            retrieved_at=observed_at,
            as_of=requested_date,
            coverage={"kind": "current_raw_snapshot_only", "historical": False},
            content_sha256=sha256(document.encode("utf-8")).hexdigest(),
        ),
    )
