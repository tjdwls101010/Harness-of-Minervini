"""Shared fixtures for operations."""

from __future__ import annotations

from tests.providers import rows_snapshot
from datetime import date, datetime, timezone
import numpy as np
import pandas as pd
from scripts.minervini.providers import ProviderSnapshot


AS_OF = "2025-12-31"


def price_snapshot(*, rising: bool = True, as_of: str = AS_OF) -> ProviderSnapshot[pd.DataFrame]:
    values = np.linspace(50, 150, 270) if rising else np.linspace(180, 80, 270)
    index = pd.bdate_range(end=as_of, periods=len(values))
    close = pd.Series(values, index=index)
    frame = pd.DataFrame(
        {
            "Open": close * 0.995,
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
            "Volume": np.full(len(close), 1_000_000),
        },
        index=index,
    )
    return rows_snapshot(frame, provider="fixture-prices", retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date.fromisoformat(as_of), coverage={"completed_only": True})


def stale_price_snapshot(*, as_of: str = AS_OF) -> ProviderSnapshot[pd.DataFrame]:
    """A history the provider could only complete through the session before as_of."""

    snapshot = price_snapshot(as_of="2025-12-30")
    return rows_snapshot(snapshot.data, provider="fixture-prices", retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date(2025, 12, 30), coverage={"completed_only": True, "requested_session": as_of, "last_completed_bar": "2025-12-30"}, stale=True)


def rs_snapshot(*, as_of: str = AS_OF) -> ProviderSnapshot[dict[str, object]]:
    return rows_snapshot({"ticker": "TEST", "rating": 94, "rating_date": as_of}, provider="fixture-rs", retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date.fromisoformat(as_of), provider_version="0.5.0")


def list_snapshot(provider: str, data: list[dict[str, object]]) -> ProviderSnapshot[list[dict[str, object]]]:
    return rows_snapshot(data, provider=provider, retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date.fromisoformat(AS_OF), provider_version="0.5.0" if provider == "ibd-rs-rating" else None)


def classification_snapshot() -> ProviderSnapshot[dict[str, str]]:
    return rows_snapshot({
            "symbol": "TEST",
            "sector": "Technology",
            "industry": "Semiconductors",
            "industry_id": "yfinance:technology:semiconductors",
        }, provider="yfinance", retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc), as_of=date(2026, 1, 2), coverage={"kind": "current_classification_only", "historical": False})
