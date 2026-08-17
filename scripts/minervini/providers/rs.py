from __future__ import annotations

from datetime import date, datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Callable

from . import ProviderSnapshot, ProviderUnavailable, SnapshotMeta, fetch_with_one_retry


PACKAGE_NAME = "ibd-rs-rating"
REQUIRED_PACKAGE_VERSION = "0.5.0"


def _as_date(value: str | date) -> date:
    return value if isinstance(value, date) else date.fromisoformat(value)


def _client() -> Any:
    from rs_rating import RS

    return RS()


def _package_version(override: str | None, *, operation: str = "rating") -> str:
    if override is not None:
        return override
    try:
        return version(PACKAGE_NAME)
    except PackageNotFoundError as error:
        raise ProviderUnavailable(PACKAGE_NAME, "package_unavailable", operation=operation) from error


def _group_snapshot_context(
    as_of: str | date | None,
    *,
    client: Any,
    package_version: str | None,
    max_staleness_days: int,
    now: date | datetime | None,
    operation: str,
) -> tuple[str, date, str, dict[str, Any]]:
    installed_version = _package_version(package_version, operation=operation)
    if installed_version != REQUIRED_PACKAGE_VERSION:
        raise ProviderUnavailable(PACKAGE_NAME, "unsupported_package_version", operation=operation)
    dates = fetch_with_one_retry(PACKAGE_NAME, "dates", client.dates)
    if not isinstance(dates, dict):
        raise ProviderUnavailable(PACKAGE_NAME, "invalid_dates_schema", operation=operation)
    first, last = dates.get("first"), dates.get("last")
    if not isinstance(first, str) or not isinstance(last, str):
        raise ProviderUnavailable(PACKAGE_NAME, "declared_date_range_unavailable", operation=operation)
    try:
        first_date, last_date = _as_date(first), _as_date(last)
    except ValueError as error:
        raise ProviderUnavailable(PACKAGE_NAME, "invalid_dates_schema", operation=operation) from error
    if first_date > last_date:
        raise ProviderUnavailable(PACKAGE_NAME, "invalid_dates_schema", operation=operation)

    requested_date = _as_date(as_of) if as_of is not None else last_date
    if requested_date < first_date or requested_date > last_date:
        raise ProviderUnavailable(PACKAGE_NAME, "requested_date_outside_declared_range", operation=operation)
    today = now.date() if isinstance(now, datetime) else now or date.today()
    if as_of is None and (today - requested_date).days > max_staleness_days:
        raise ProviderUnavailable(PACKAGE_NAME, "stale_snapshot", operation=operation)
    return (
        installed_version,
        requested_date,
        requested_date.isoformat(),
        {
            "kind": "library_declared_date_range",
            "first": first_date.isoformat(),
            "last": last_date.isoformat(),
            "universe": "library_not_declared",
            "complete": None,
        },
    )


def _group_snapshot(
    *,
    as_of: str | date | None,
    client: Any | None,
    package_version: str | None,
    max_staleness_days: int,
    now: date | datetime | None,
    retrieved_at: datetime | None,
    operation: str,
    fetch: Callable[[Any, str], Any],
    validate: Callable[[Any], list[dict[str, Any]] | None],
) -> ProviderSnapshot[list[dict[str, Any]]]:
    rs_client = client if client is not None else _client()
    installed_version, requested_date, requested, coverage = _group_snapshot_context(
        as_of,
        client=rs_client,
        package_version=package_version,
        max_staleness_days=max_staleness_days,
        now=now,
        operation=operation,
    )
    records = fetch_with_one_retry(PACKAGE_NAME, operation, lambda: fetch(rs_client, requested))
    if records is None:
        raise ProviderUnavailable(PACKAGE_NAME, f"{operation}_missing", operation=operation)
    normalized = validate(records)
    if normalized is None:
        raise ProviderUnavailable(PACKAGE_NAME, f"invalid_{operation}_schema", operation=operation)
    return ProviderSnapshot(
        data=normalized,
        meta=SnapshotMeta(
            provider=PACKAGE_NAME,
            retrieved_at=retrieved_at or datetime.now(timezone.utc),
            as_of=requested_date,
            provider_version=installed_version,
            coverage=coverage,
            stale=False,
        ),
    )


def _valid_records(value: Any, required_fields: dict[str, Any]) -> list[dict[str, Any]] | None:
    if not isinstance(value, list):
        return None
    records: list[dict[str, Any]] = []
    for record in value:
        if not isinstance(record, dict):
            return None
        for field, expected_type in required_fields.items():
            field_value = record.get(field)
            if not isinstance(field_value, expected_type) or isinstance(field_value, bool):
                return None
            if expected_type is str and not field_value:
                return None
        records.append(dict(record))
    return records


def sector_ranking_snapshot(
    as_of: str | date | None = None,
    *,
    client: Any | None = None,
    package_version: str | None = None,
    max_staleness_days: int = 5,
    now: date | datetime | None = None,
    retrieved_at: datetime | None = None,
) -> ProviderSnapshot[list[dict[str, Any]]]:
    """Read library-provided sector RS rankings for one declared RS date."""

    return _group_snapshot(
        as_of=as_of,
        client=client,
        package_version=package_version,
        max_staleness_days=max_staleness_days,
        now=now,
        retrieved_at=retrieved_at,
        operation="sector_ranking",
        fetch=lambda rs_client, requested: rs_client.sector_ranking(date=requested),
        validate=lambda records: _valid_records(records, {"sector": str, "avg_rs": (int, float), "count": int}),
    )


def industry_ranking_snapshot(
    as_of: str | date | None = None,
    *,
    sector: str | None = None,
    client: Any | None = None,
    package_version: str | None = None,
    max_staleness_days: int = 5,
    now: date | datetime | None = None,
    retrieved_at: datetime | None = None,
) -> ProviderSnapshot[list[dict[str, Any]]]:
    """Read library-provided industry RS rankings for one declared RS date."""

    return _group_snapshot(
        as_of=as_of,
        client=client,
        package_version=package_version,
        max_staleness_days=max_staleness_days,
        now=now,
        retrieved_at=retrieved_at,
        operation="industry_ranking",
        fetch=lambda rs_client, requested: rs_client.industry_ranking(date=requested, sector=sector),
        validate=lambda records: _valid_records(records, {"industry": str, "sector": str, "avg_rs": (int, float), "count": int}),
    )


def industry_top_snapshot(
    industry: str,
    as_of: str | date | None = None,
    *,
    n: int = 20,
    client: Any | None = None,
    package_version: str | None = None,
    max_staleness_days: int = 5,
    now: date | datetime | None = None,
    retrieved_at: datetime | None = None,
) -> ProviderSnapshot[list[dict[str, Any]]]:
    """Read library-provided top RS stocks for one industry and declared RS date."""

    return _group_snapshot(
        as_of=as_of,
        client=client,
        package_version=package_version,
        max_staleness_days=max_staleness_days,
        now=now,
        retrieved_at=retrieved_at,
        operation="industry_top",
        fetch=lambda rs_client, requested: rs_client.industry_top(industry, n=n, date=requested),
        validate=lambda records: _valid_records(records, {"ticker": str, "rs_rating": (int, float), "rs_raw": (int, float)}),
    )


def top_snapshot(
    as_of: str | date | None = None,
    *,
    n: int = 20,
    client: Any | None = None,
    package_version: str | None = None,
    max_staleness_days: int = 5,
    now: date | datetime | None = None,
    retrieved_at: datetime | None = None,
) -> ProviderSnapshot[list[dict[str, Any]]]:
    """Read library-provided top RS stocks for one declared RS date."""

    return _group_snapshot(
        as_of=as_of,
        client=client,
        package_version=package_version,
        max_staleness_days=max_staleness_days,
        now=now,
        retrieved_at=retrieved_at,
        operation="top",
        fetch=lambda rs_client, requested: rs_client.top(n=n, date=requested),
        validate=lambda records: _valid_records(records, {"ticker": str, "rs_rating": (int, float), "rs_raw": (int, float)}),
    )


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
