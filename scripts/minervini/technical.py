"""Turn one completed price snapshot into eligibility claim evidence."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd

from .eligibility import TREND_TEMPLATE_CRITERIA


DOCTRINE_TREND = "eligibility.standard_trend_template"
DOCTRINE_STAGE = "eligibility.standard_stage2"
DOCTRINE_IPO = "eligibility.recent_ipo_primary_base"


def _signal(identifier: str, state: str, measured: Any, required: str, doctrine_id: str = DOCTRINE_TREND) -> dict[str, Any]:
    return {
        "id": identifier,
        "state": state,
        "doctrine_id": doctrine_id,
        "basis": {"measured": measured, "required": required},
    }


def _comparison(identifier: str, measured: float | None, comparator: float | None, required: str) -> dict[str, Any]:
    if measured is None or comparator is None:
        return _signal(identifier, "unavailable", measured, required)
    return _signal(identifier, "pass" if measured > comparator else "fail", round(measured, 4), required)


def _sma(close: pd.Series, length: int) -> float | None:
    if len(close) < length:
        return None
    return float(close.rolling(length).mean().iloc[-1])


def _primary_base(close: pd.Series, quality: str | None) -> dict[str, Any]:
    count = len(close)
    prior = close.iloc[:-1]
    claims: list[dict[str, Any]] = []
    claims.append(_signal("primary_base.minimum_history", "pass" if count >= 40 else "fail", count, ">= 40 completed sessions", DOCTRINE_IPO))
    if prior.empty:
        duration = None
        depth = None
        ath_breakout = None
    else:
        prior_peak = float(prior.max())
        peak_position = int(prior.to_numpy().argmax())
        duration = count - 1 - peak_position
        base_slice = prior.iloc[peak_position:]
        depth = (prior_peak - float(base_slice.min())) / prior_peak * 100 if prior_peak > 0 else None
        ath_breakout = float(close.iloc[-1]) > prior_peak
    claims.append(_signal("primary_base.minimum_duration", "unavailable" if duration is None else "pass" if duration >= 15 else "fail", duration, ">= 15 completed sessions", DOCTRINE_IPO))
    if depth is None or duration is None:
        depth_state = "unavailable"
        depth_required = "source-defined duration/depth band"
    elif duration <= 15:
        depth_state = "pass" if depth <= 25 else "fail"
        depth_required = "<= 25% for a three-week base"
    elif duration >= 25:
        depth_state = "pass" if depth <= 35 else "fail"
        depth_required = "<= 35% for a five-week-or-longer base"
    else:
        depth_state = "unavailable"
        depth_required = "manual review in the source's three-to-five-week transition band"
    claims.append(_signal("primary_base.duration_depth", depth_state, round(depth, 4) if depth is not None else None, depth_required, DOCTRINE_IPO))
    claims.append(_signal("primary_base.all_time_high_breakout", "unavailable" if ath_breakout is None else "pass" if ath_breakout else "fail", float(close.iloc[-1]) if count else None, "close above all prior completed-session highs", DOCTRINE_IPO))
    quality_state = quality if quality in {"supports", "contradicts", "needs_chart"} else "needs_chart"
    return {
        "quantitative_claims": claims,
        "quality": {
            "id": "primary_base.visual_quality",
            "state": quality_state,
            "doctrine_id": DOCTRINE_IPO,
            "basis": {"measured": quality, "required": "model review of the weekly chart before eligibility"},
        },
    }


def build_eligibility_evidence(
    history: pd.DataFrame,
    *,
    rs_rating: int | None,
    primary_base_quality: str | None = None,
) -> dict[str, Any]:
    """Build the canonical eight claims from completed daily bars only.

    The price provider owns session completion and as-of filtering. This
    function rejects missing OHLC evidence and never reaches a provider itself.
    """
    if not isinstance(history, pd.DataFrame) or "Close" not in history:
        raise ValueError("history must be a DataFrame with a Close column")
    close = pd.to_numeric(history["Close"], errors="coerce").dropna()
    if close.empty:
        raise ValueError("history contains no completed closing prices")
    if not close.index.is_monotonic_increasing:
        close = close.sort_index()

    current = float(close.iloc[-1])
    sma50, sma150, sma200 = (_sma(close, length) for length in (50, 150, 200))
    sma200_month_ago = float(close.iloc[:-21].rolling(200).mean().iloc[-1]) if len(close) >= 221 else None
    window = close.tail(min(252, len(close)))
    low_52, high_52 = float(window.min()), float(window.max())
    above_low_pct = (current / low_52 - 1) * 100 if low_52 > 0 else None
    below_high_pct = (1 - current / high_52) * 100 if high_52 > 0 else None

    first_state = "unavailable" if sma150 is None or sma200 is None else "pass" if current > sma150 and current > sma200 else "fail"
    trend = [
        _signal(TREND_TEMPLATE_CRITERIA[0], first_state, round(current, 4), "price > 150 SMA and 200 SMA"),
        _comparison(TREND_TEMPLATE_CRITERIA[1], sma150, sma200, "150 SMA > 200 SMA"),
        _signal(TREND_TEMPLATE_CRITERIA[2], "unavailable" if sma200 is None or sma200_month_ago is None else "pass" if sma200 > sma200_month_ago else "fail", round(sma200, 4) if sma200 is not None else None, "200 SMA higher than 21 completed sessions earlier"),
        _signal(TREND_TEMPLATE_CRITERIA[3], "unavailable" if sma50 is None or sma150 is None or sma200 is None else "pass" if sma50 > sma150 and sma50 > sma200 else "fail", round(sma50, 4) if sma50 is not None else None, "50 SMA > 150 SMA and 200 SMA"),
        _signal(TREND_TEMPLATE_CRITERIA[4], "unavailable" if above_low_pct is None else "pass" if above_low_pct >= 30 else "fail", round(above_low_pct, 4) if above_low_pct is not None else None, ">= 30% above 52-week low"),
        _signal(TREND_TEMPLATE_CRITERIA[5], "unavailable" if below_high_pct is None else "pass" if below_high_pct <= 25 else "fail", round(below_high_pct, 4) if below_high_pct is not None else None, "within 25% of 52-week high"),
        _signal(TREND_TEMPLATE_CRITERIA[6], "unavailable" if rs_rating is None else "pass" if 1 <= rs_rating <= 99 and rs_rating >= 70 else "fail", rs_rating, "first-party SEPA RS percentile >= 70"),
        _comparison(TREND_TEMPLATE_CRITERIA[7], current, sma50, "price > 50 SMA"),
    ]
    history_state = "sufficient" if len(close) >= 200 else "insufficient"
    if history_state == "sufficient":
        stage_state = "pass" if all(signal["state"] == "pass" for signal in (trend[0], trend[1], trend[2], trend[3], trend[7])) else "fail" if any(signal["state"] == "fail" for signal in (trend[0], trend[1], trend[2], trend[3], trend[7])) else "unavailable"
    else:
        stage_state = "unavailable"
    result: dict[str, Any] = {
        "as_of": close.index[-1].date().isoformat() if hasattr(close.index[-1], "date") else str(close.index[-1]),
        "history_state": history_state,
        "stage_2": _signal("stage_2.confirmed_advance", stage_state, None, "confirmed Stage 2 structure", DOCTRINE_STAGE),
        "trend_template": trend,
    }
    if history_state == "insufficient":
        result["primary_base"] = _primary_base(close, primary_base_quality)
    return result


__all__ = ["build_eligibility_evidence"]
