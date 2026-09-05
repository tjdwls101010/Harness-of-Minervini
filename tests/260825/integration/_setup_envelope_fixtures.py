"""Shared fixtures for setup envelope."""

from __future__ import annotations

from tests.providers import rows_snapshot
from datetime import datetime, timezone
from scripts.minervini.operations import Runtime, execute
from scripts.minervini.providers import ProviderSnapshot
from scripts.minervini.setup_structure import bars_fingerprint
from tests.series import anchor_dates, base_series


def snapshot(**kwargs) -> tuple[ProviderSnapshot, list[str]]:
    frame, anchors = base_series(**kwargs)

    return rows_snapshot(frame, provider="fixture-prices", retrieved_at=datetime(2026, 7, 1, tzinfo=timezone.utc), as_of=frame.index[-1].date(), coverage={"completed_only": True}), anchor_dates(frame, anchors)


def run(*, swings=None, as_of=None, approved_bars=None, chain_completeness="complete", **kwargs) -> dict:
    completeness = chain_completeness
    prices, chain = snapshot(**kwargs)
    runtime = Runtime(price_history=lambda ticker, requested: prices)
    request = {
        "ticker": "TEST",
        "as_of": as_of or prices.meta.as_of.isoformat(),
        "swing": chain if swings is None else swings,
        "right_side_development": "constructive",
        "chain_completeness": completeness,
        "approved_bars": approved_bars or bars_fingerprint(prices.data),
        "entry_proximity": "at_pivot",
        "entry_price": float(prices.data["Close"].iloc[-1]),
        "no_cache": True,
    }
    return execute("ticker.setup", request, runtime=runtime)
