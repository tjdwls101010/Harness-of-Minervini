"""Build same-industry comparison rows from already-collected evidence."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date
from math import isfinite
from typing import Any

import pandas as pd

from .providers.nasdaq import SecurityRecord


_EXCHANGE_ALIASES = {
    "NYSE AMERICAN": "NYSEAMERICAN",
    "NYSE NATIONAL": "NYSE",
    "CBOE BZX": "CBOE",
}


def collect_same_industry_peer_rows(
    target_classification: Mapping[str, Any],
    security_universe: Iterable[SecurityRecord],
    industry_top_rows: Iterable[Mapping[str, Any]],
    target_rs_rating: Mapping[str, Any] | int | float,
    completed_prices: Mapping[str, pd.DataFrame],
    *,
    as_of: str,
) -> dict[str, Any]:
    """Return target and candidate rows accepted by ``compare_same_industry_peers``.

    All inputs are already collected snapshots. The sole identity source is the
    current Nasdaq security master; a symbol absent from it is reported rather
    than assigned a synthetic instrument ID. ``industry_top_rows`` is assumed
    to be the requested exact-date IBD RS snapshot, while each price frame is
    completed yfinance daily data.
    """
    analysis_date = _as_date(as_of)
    target_symbol = _required_text(target_classification, "symbol")
    industry_id = _required_text(target_classification, "industry_id")
    records_by_symbol, ambiguous_symbols = _records_by_symbol(security_universe)
    missing: list[dict[str, str]] = []

    target_record = _record_for_symbol(target_symbol, records_by_symbol, ambiguous_symbols, missing)
    target = (
        _row(
            target_record,
            industry_id,
            _rating_evidence(target_rs_rating, analysis_date),
            _price_evidence(completed_prices.get(target_symbol), analysis_date),
        )
        if target_record is not None
        else None
    )

    candidates: list[dict[str, Any]] = []
    seen_symbols = {target_symbol}
    for source_row in industry_top_rows:
        symbol = _industry_symbol(source_row)
        if symbol is None or symbol in seen_symbols:
            continue
        seen_symbols.add(symbol)
        record = _record_for_symbol(symbol, records_by_symbol, ambiguous_symbols, missing)
        if record is None:
            continue
        rating = source_row.get("rs_rating")
        candidates.append(
            _row(
                record,
                industry_id,
                _rating_evidence(rating, analysis_date),
                _price_evidence(completed_prices.get(symbol), analysis_date),
            )
        )

    return {"target": target, "candidates": candidates, "missing": missing}


def _as_date(value: str) -> date:
    if not isinstance(value, str):
        raise ValueError("as_of must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("as_of must be an ISO date") from error


def _required_text(row: Mapping[str, Any], field: str) -> str:
    value = row.get(field) if isinstance(row, Mapping) else None
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"target_classification requires {field}")
    return value.upper() if field == "symbol" else value


def _records_by_symbol(records: Iterable[SecurityRecord]) -> tuple[dict[str, SecurityRecord], set[str]]:
    grouped: dict[str, list[SecurityRecord]] = {}
    for record in records:
        if not isinstance(record, SecurityRecord):
            raise ValueError("security_universe must contain SecurityRecord values")
        grouped.setdefault(record.symbol.upper(), []).append(record)
    return (
        {symbol: members[0] for symbol, members in grouped.items() if len(members) == 1},
        {symbol for symbol, members in grouped.items() if len(members) > 1},
    )


def _record_for_symbol(
    symbol: str,
    records: Mapping[str, SecurityRecord],
    ambiguous_symbols: set[str],
    missing: list[dict[str, str]],
) -> SecurityRecord | None:
    if symbol in ambiguous_symbols:
        missing.append({"ticker": symbol, "reason": "ambiguous_security_master_symbol"})
        return None
    record = records.get(symbol)
    if record is None:
        missing.append({"ticker": symbol, "reason": "absent_from_security_master"})
    return record


def _industry_symbol(row: Mapping[str, Any]) -> str | None:
    value = row.get("ticker") if isinstance(row, Mapping) else None
    if not isinstance(value, str):
        return None
    symbol = value.strip().upper()
    return symbol or None


def _row(
    record: SecurityRecord,
    industry_id: str,
    rs_evidence: dict[str, Any] | None,
    price_evidence: dict[str, Any] | None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "instrument_id": record.instrument_id,
        "ticker": record.symbol,
        "industry_id": industry_id,
        "exchange": _EXCHANGE_ALIASES.get(record.exchange.upper(), record.exchange.upper()),
        "listing_country": "US",
        "instrument_type": record.instrument_type,
        "is_adr": record.is_adr,
    }
    if rs_evidence is not None:
        row["rs_evidence"] = rs_evidence
    if price_evidence is not None:
        row["price_evidence"] = price_evidence
    return row


def _rating_evidence(value: Mapping[str, Any] | int | float, as_of: date) -> dict[str, Any] | None:
    declared_date: Any = as_of.isoformat()
    rating: Any = value
    if isinstance(value, Mapping):
        rating = value.get("rating", value.get("rs_rating"))
        declared_date = value.get("rating_date", value.get("as_of", as_of.isoformat()))
    if declared_date != as_of.isoformat() or not _positive_number(rating) or not 1 <= float(rating) <= 99:
        return None
    return {"provider": "ibd-rs-rating", "as_of": as_of.isoformat(), "rating": float(rating)}


def _price_evidence(frame: pd.DataFrame | None, as_of: date) -> dict[str, Any] | None:
    if not isinstance(frame, pd.DataFrame) or "Close" not in frame:
        return None
    closes = pd.to_numeric(frame["Close"], errors="coerce")
    dates = pd.to_datetime(frame.index, errors="coerce")
    normalized = pd.DataFrame({"date": dates.to_numpy(), "close": closes.to_numpy()}).dropna()
    if normalized.empty:
        return None
    if getattr(normalized["date"].dt, "tz", None) is not None:
        normalized["date"] = normalized["date"].dt.tz_convert("America/New_York").dt.tz_localize(None)
    normalized = normalized[(normalized["date"].dt.date <= as_of) & (normalized["close"] > 0)].sort_values("date")
    if normalized.empty or normalized.iloc[-1]["date"].date() != as_of:
        return None
    cutoff_3m = pd.Timestamp(as_of) - pd.DateOffset(months=3)
    three_month_start = normalized[normalized["date"] <= cutoff_3m]
    year_window = normalized[normalized["date"] >= pd.Timestamp(as_of) - pd.DateOffset(weeks=52)]
    if three_month_start.empty or year_window.empty:
        return None
    current = float(normalized.iloc[-1]["close"])
    start = float(three_month_start.iloc[-1]["close"])
    high = float(year_window["close"].max())
    if not all(isfinite(number) and number > 0 for number in (current, start, high)):
        return None
    return {
        "provider": "yfinance",
        "as_of": as_of.isoformat(),
        "return_3m_pct": round((current / start - 1) * 100, 4),
        "distance_from_52_week_high_pct": round((1 - current / high) * 100, 4),
    }


def _positive_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(float(value))


__all__ = ["collect_same_industry_peer_rows"]
