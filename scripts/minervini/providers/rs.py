from __future__ import annotations

from datetime import date, datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from . import ProviderSnapshot, ProviderUnavailable, SnapshotMeta, fetch_with_one_retry


PACKAGE_NAME = "ibd-rs-rating"
REQUIRED_PACKAGE_VERSION = "0.5.0"


def _as_date(value: str | date) -> date:
    return value if isinstance(value, date) else date.fromisoformat(value)


def _client() -> Any:
    from rs_rating import RS

    return RS()


def _package_version(override: str | None) -> str:
    if override is not None:
        return override
    try:
        return version(PACKAGE_NAME)
    except PackageNotFoundError as error:
        raise ProviderUnavailable(PACKAGE_NAME, "package_unavailable", operation="rating") from error


def rating_snapshot(
    ticker: str,
    *,
    as_of: str | date | None = None,
    client: Any | None = None,
    package_version: str | None = None,
    max_staleness_days: int = 5,
    now: date | datetime | None = None,
    retrieved_at: datetime | None = None,
) -> ProviderSnapshot[dict[str, Any]]:
    """Read an exact library-provided RS rating without deriving a proxy formula."""

    installed_version = _package_version(package_version)
    if installed_version != REQUIRED_PACKAGE_VERSION:
        raise ProviderUnavailable(PACKAGE_NAME, "unsupported_package_version", operation="rating")
    client = client if client is not None else _client()
    dates = fetch_with_one_retry(PACKAGE_NAME, "dates", client.dates)
    first, last = dates.get("first"), dates.get("last")
    if not first or not last:
        raise ProviderUnavailable(PACKAGE_NAME, "declared_date_range_unavailable", operation="rating")

    requested_date = _as_date(as_of) if as_of is not None else _as_date(last)
    requested = requested_date.isoformat()
    record = fetch_with_one_retry(
        PACKAGE_NAME,
        "get",
        lambda: client.get(ticker.upper(), date=requested),
    )
    if not isinstance(record, dict) or record.get("rs_rating") is None:
        raise ProviderUnavailable(PACKAGE_NAME, "rating_missing", operation="rating")
    rating_date = _as_date(record.get("date", requested))
    if rating_date != requested_date:
        raise ProviderUnavailable(PACKAGE_NAME, "rating_date_mismatch", operation="rating")

    today = now.date() if isinstance(now, datetime) else now or date.today()
    stale = as_of is None and (today - rating_date).days > max_staleness_days
    if stale:
        raise ProviderUnavailable(PACKAGE_NAME, "stale_snapshot", operation="rating")

    coverage = {
        "kind": "library_declared_date_range",
        "first": first,
        "last": last,
        "universe": "library_not_declared",
        "complete": None,
    }
    observed_at = retrieved_at or datetime.now(timezone.utc)
    return ProviderSnapshot(
        data={"ticker": ticker.upper(), "rating": int(record["rs_rating"]), "rating_date": rating_date.isoformat()},
        meta=SnapshotMeta(
            provider=PACKAGE_NAME,
            retrieved_at=observed_at,
            as_of=requested_date,
            provider_version=installed_version,
            coverage=coverage,
            stale=False,
        ),
    )
