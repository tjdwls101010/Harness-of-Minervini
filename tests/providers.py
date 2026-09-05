"""Provider snapshots whose evidence and metadata are explicit in the test."""

from datetime import date, datetime, timezone
from typing import Any, Mapping

from scripts.minervini.providers import ProviderSnapshot, SnapshotMeta


def price_snapshot(data: Any, *, as_of: str | date | None, provider: str = "fixture-prices", retrieved_at: datetime = datetime(2026, 1, 2, tzinfo=timezone.utc), coverage: Mapping[str, Any] | None = None, **metadata: Any) -> ProviderSnapshot:
    return ProviderSnapshot(data, SnapshotMeta(provider=provider, retrieved_at=retrieved_at, as_of=date.fromisoformat(as_of) if isinstance(as_of, str) else as_of, coverage={"completed_only": True} if coverage is None else coverage, **metadata))


def rows_snapshot(data: Any, *, as_of: str | date | None, provider: str, coverage: Mapping[str, Any] | None = None, **metadata: Any) -> ProviderSnapshot:
    return price_snapshot(data, as_of=as_of, provider=provider, coverage={} if coverage is None else coverage, **metadata)
