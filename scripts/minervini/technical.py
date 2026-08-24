"""Turn one completed price snapshot into eligibility claim evidence."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd

from . import doctrine
from .eligibility import TREND_TEMPLATE_CRITERIA


DOCTRINE_TREND = "eligibility.standard_trend_template"
DOCTRINE_STAGE = "eligibility.standard_stage2"
DOCTRINE_IPO = "eligibility.recent_ipo_primary_base"
# Completed US sessions in a calendar month, used only to read a source duration the
# book states in months into the bar count this module actually counts.
_SESSIONS_PER_MONTH = 21


def _signal(identifier: str, state: str, measured: Any, required: str, doctrine_id: str = DOCTRINE_TREND) -> dict[str, Any]:
    return {
        "id": identifier,
        "state": state,
        "doctrine_id": doctrine_id,
        "basis": {"measured": measured, "required": required},
    }


def _gate(identifier: str, name: str, measured: float | None, doctrine_id: str = DOCTRINE_TREND) -> dict[str, Any]:
    """Decide one criterion with the registry's own number and the registry's own wording.

    Reading both from the same place is what keeps the limit a verdict used and the
    limit its help text advertises from ever being two different numbers.
    """
    gate = doctrine.evaluate_gate(doctrine_id, name, measured)
    return _signal(identifier, gate["state"], gate["measured"], gate["required"], doctrine_id)


def _comparison(identifier: str, measured: float | None, comparator: float | None, required: str) -> dict[str, Any]:
    if measured is None or comparator is None:
        return _signal(identifier, "unavailable", measured, required)
    return _signal(identifier, "pass" if measured > comparator else "fail", round(measured, 4), required)


def _sma(close: pd.Series, length: int) -> float | None:
    if len(close) < length:
        return None
    return float(close.rolling(length).mean().iloc[-1])


def _depth_claim(depth: float | None, duration: int | None, long_correction: str | None) -> dict[str, Any]:
    """Apply the depth rule the base's own duration selects.

    The source states one ceiling for a three-week consolidation, a range for a three-
    to-five-week base, and a deeper allowance for a correction lasting about a year. It
    never says how many sessions "about a year" is, so that last case is confirmed from
    the weekly chart instead of resolved with a cutoff nobody wrote down.
    """
    if depth is None or duration is None:
        return _signal("primary_base.duration_depth", "unavailable", depth, "source-defined duration/depth band", DOCTRINE_IPO)
    measured = round(depth, 4)
    three_weeks = doctrine.threshold(DOCTRINE_IPO, "minimum_base_duration_sessions")
    five_weeks = doctrine.threshold(DOCTRINE_IPO, "five_week_base_duration_sessions")
    if duration <= three_weeks:
        return _gate("primary_base.duration_depth", "three_week_base_depth_pct", measured, DOCTRINE_IPO)
    band = doctrine.evaluate_band(DOCTRINE_IPO, "three_to_five_week_base_depth_pct", measured)
    if duration <= five_weeks:
        return _signal("primary_base.duration_depth", "pass" if band["state"] == "within_source_range" else "fail", measured, f"within {band['source_range']}% for a three-to-five-week base", DOCTRINE_IPO)
    if band["state"] == "within_source_range":
        return _signal("primary_base.duration_depth", "pass", measured, f"within {band['source_range']}% for a base longer than five weeks", DOCTRINE_IPO)
    year_long = _gate("primary_base.duration_depth", "year_long_correction_depth_pct", measured, DOCTRINE_IPO)
    if year_long["state"] == "fail":
        return year_long
    resolved = {"confirmed": "pass", "not_confirmed": "fail"}.get(str(long_correction), "unavailable")
    return _signal("primary_base.duration_depth", resolved, measured, f"deeper than {band['source_range'][1]}% needs weekly-chart confirmation that the correction lasted about a year", DOCTRINE_IPO)


def _primary_base(
    close: pd.Series,
    quality: str | None,
    emergence_judgment: str | None,
    long_correction: str | None,
) -> dict[str, Any]:
    count = len(close)
    prior = close.iloc[:-1]
    claims: list[dict[str, Any]] = []
    claims.append(_gate("primary_base.minimum_history", "minimum_trading_history_sessions", count, DOCTRINE_IPO))
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
    claims.append(_gate("primary_base.minimum_duration", "minimum_base_duration_sessions", duration, DOCTRINE_IPO))
    claims.append(_depth_claim(depth, duration, long_correction))
    quality_state = quality if quality in {"supports", "contradicts", "needs_chart"} else "needs_chart"
    return {
        "quantitative_claims": claims,
        # The source accepts emergence to an all-time high or from a constructive
        # consolidation near it, so an unbroken high is timing that has not happened
        # yet, and the second route needs the caller's chart confirmation.
        "emergence": _signal(
            "primary_base.emergence",
            "unavailable"
            if ath_breakout is None
            else "pass"
            if ath_breakout or emergence_judgment == "near_high_consolidation"
            else "not_triggered",
            float(close.iloc[-1]) if count else None,
            "close above all prior completed-session highs, or a chart-confirmed constructive consolidation near them",
            DOCTRINE_IPO,
        ),
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
    primary_base_emergence: str | None = None,
    primary_base_long_correction: str | None = None,
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
    # The source states the 200-day average must have been rising for at least a month;
    # the session count is this module's reading of "a month", so it is derived here
    # rather than hard-coded beside it.
    rising_sessions = round(doctrine.threshold(DOCTRINE_TREND, "sma_200_rising_minimum_months") * _SESSIONS_PER_MONTH)
    sma200_month_ago = float(close.iloc[:-rising_sessions].rolling(200).mean().iloc[-1]) if len(close) >= 200 + rising_sessions else None
    window = close.tail(min(252, len(close)))
    low_52, high_52 = float(window.min()), float(window.max())
    above_low_pct = (current / low_52 - 1) * 100 if low_52 > 0 else None
    below_high_pct = (1 - current / high_52) * 100 if high_52 > 0 else None

    first_state = "unavailable" if sma150 is None or sma200 is None else "pass" if current > sma150 and current > sma200 else "fail"
    trend = [
        _signal(TREND_TEMPLATE_CRITERIA[0], first_state, round(current, 4), "price > 150 SMA and 200 SMA"),
        _comparison(TREND_TEMPLATE_CRITERIA[1], sma150, sma200, "150 SMA > 200 SMA"),
        _signal(TREND_TEMPLATE_CRITERIA[2], "unavailable" if sma200 is None or sma200_month_ago is None else "pass" if sma200 > sma200_month_ago else "fail", round(sma200, 4) if sma200 is not None else None, f"200 SMA higher than {rising_sessions} completed sessions earlier"),
        _signal(TREND_TEMPLATE_CRITERIA[3], "unavailable" if sma50 is None or sma150 is None or sma200 is None else "pass" if sma50 > sma150 and sma50 > sma200 else "fail", round(sma50, 4) if sma50 is not None else None, "50 SMA > 150 SMA and 200 SMA"),
        _comparison(TREND_TEMPLATE_CRITERIA[4], current, sma50, "price > 50 SMA"),
        _gate(TREND_TEMPLATE_CRITERIA[5], "minimum_pct_above_52_week_low", round(above_low_pct, 4) if above_low_pct is not None else None),
        _gate(TREND_TEMPLATE_CRITERIA[6], "maximum_pct_below_52_week_high", round(below_high_pct, 4) if below_high_pct is not None else None),
        _gate(TREND_TEMPLATE_CRITERIA[7], "relative_strength_minimum", rs_rating if rs_rating is None or 1 <= rs_rating <= 99 else -1),
    ]
    history_state = "sufficient" if len(close) >= 200 else "insufficient"
    if history_state == "sufficient":
        stage_signals = (trend[0], trend[1], trend[2], trend[3], trend[4])
        stage_state = "pass" if all(signal["state"] == "pass" for signal in stage_signals) else "fail" if any(signal["state"] == "fail" for signal in stage_signals) else "unavailable"
    else:
        stage_state = "unavailable"
    result: dict[str, Any] = {
        "as_of": close.index[-1].date().isoformat() if hasattr(close.index[-1], "date") else str(close.index[-1]),
        "history_state": history_state,
        "stage_2": _signal("stage_2.confirmed_advance", stage_state, None, "confirmed Stage 2 structure", DOCTRINE_STAGE),
        "trend_template": trend,
    }
    if history_state == "insufficient":
        result["primary_base"] = _primary_base(close, primary_base_quality, primary_base_emergence, primary_base_long_correction)
    return result


__all__ = ["build_eligibility_evidence"]
