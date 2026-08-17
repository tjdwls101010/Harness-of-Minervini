"""Reduce completed daily bars and chart review into setup-evaluator evidence."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

import pandas as pd


_REQUIRED_COLUMNS = ("Open", "High", "Low", "Close", "Volume")
_PIVOT_LOOKBACK = 20
_POSITIVE_STATES = {"pass", "ready", "confirmed", "eligible", "supports", "observed", "complete"}


def _copy_mapping(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _state(value: Any, default: str) -> str:
    if isinstance(value, Mapping):
        value = value.get("state", value.get("status"))
    if value is None:
        return default
    return str(value).strip().lower().replace("-", "_") or default


def _chart_claim(value: Any, default: str = "needs_chart") -> dict[str, Any]:
    claim = _copy_mapping(value)
    claim["state"] = _state(claim, default)
    return claim


def _unavailable_evidence(reason: str) -> dict[str, Any]:
    return {
        "price_geometry": {"state": "unavailable", "reason": reason},
        "supply_evidence": {"state": "unavailable", "reason": reason},
        "entry": {"kind": None, "state": "unavailable", "reason": reason},
        "vcp_label": None,
    }


def _completed_bars(history: Any) -> pd.DataFrame | None:
    if not isinstance(history, pd.DataFrame) or any(column not in history for column in _REQUIRED_COLUMNS):
        return None
    bars = history.loc[:, _REQUIRED_COLUMNS].copy()
    for column in _REQUIRED_COLUMNS:
        bars[column] = pd.to_numeric(bars[column], errors="coerce")
    if bars.isna().any().any() or (bars.loc[:, _REQUIRED_COLUMNS] <= 0).any().any():
        return None
    if not bars.index.is_monotonic_increasing:
        bars = bars.sort_index()
    return bars


def _volume_observation(bars: pd.DataFrame) -> dict[str, Any]:
    if len(bars) < 11:
        return {"state": "needs_chart", "reason": "insufficient completed volume history"}
    recent = float(bars["Volume"].iloc[-5:].mean())
    preceding = float(bars["Volume"].iloc[-11:-5].mean())
    return {
        "state": "needs_chart",
        "recent_5_session_average": round(recent, 4),
        "preceding_6_session_average": round(preceding, 4),
        "recent_to_preceding_ratio": round(recent / preceding, 4) if preceding > 0 else None,
        "reason": "volume observations do not establish supply absorption without chart review",
    }


def _candidate_pivot(bars: pd.DataFrame) -> dict[str, Any] | None:
    if len(bars) < _PIVOT_LOOKBACK + 1:
        return None
    prior = bars.iloc[-(_PIVOT_LOOKBACK + 1) : -1]
    return {
        "price": round(float(prior["High"].max()), 4),
        "lookback_sessions": _PIVOT_LOOKBACK,
        "basis": "highest high among the preceding completed sessions",
    }


def _add_debt(entry: dict[str, Any], item: str) -> None:
    debt = entry.get("confirmation_debt")
    items = [str(value) for value in debt if str(value).strip()] if isinstance(debt, list) else []
    if item not in items:
        items.append(item)
    entry["confirmation_debt"] = items


def _entry_evidence(
    source: Any,
    *,
    candidate_pivot: dict[str, Any] | None,
    close: float | None,
    geometry: Mapping[str, Any],
    supply: Mapping[str, Any],
    tactic_opt_in: bool,
) -> dict[str, Any]:
    if candidate_pivot is None or close is None:
        return {"kind": None, "state": "unavailable", "reason": "insufficient completed history for a candidate pivot"}

    chart_entry = _copy_mapping(source)
    kind = str(chart_entry.get("kind", "")).strip().lower().replace("-", "_")
    trigger = {
        "price": candidate_pivot["price"],
        "condition": "completed close above the candidate pivot",
    }
    invalidation = _copy_mapping(chart_entry.get("invalidation"))
    if not invalidation:
        invalidation = {"state": "needs_chart", "reason": "base low requires visual structure"}

    if kind not in {"completed_pivot", "pivot_breakout", "breakout", "vcp_cheat", "cheat", "3c_cheat", "tl_early", "early"}:
        return {
            "kind": "candidate_pivot",
            "state": "wait",
            "candidate_pivot": candidate_pivot,
            "trigger": trigger,
            "invalidation": invalidation,
            "confirmation_debt": ["chart-confirmed entry pattern"],
        }

    canonical_kind = {
        "pivot_breakout": "completed_pivot",
        "breakout": "completed_pivot",
        "cheat": "vcp_cheat",
        "3c_cheat": "vcp_cheat",
        "early": "tl_early",
    }.get(kind, kind)
    entry = {**chart_entry, "kind": canonical_kind, "candidate_pivot": candidate_pivot, "trigger": trigger, "invalidation": invalidation}
    chart_confirmed = _state(chart_entry, "unavailable") in _POSITIVE_STATES

    if canonical_kind == "tl_early":
        entry["opt_in"] = tactic_opt_in
        entry["state"] = "pass" if chart_confirmed else "wait"
        if not chart_confirmed:
            _add_debt(entry, "chart-confirmed TL early entry")
        return entry

    conditions = [
        (chart_confirmed, "chart-confirmed entry pattern"),
        (_state(geometry, "needs_chart") == "pass", "chart-confirmed price geometry"),
    ]
    if canonical_kind == "completed_pivot":
        conditions.append((close > candidate_pivot["price"], "completed_close_above_candidate_pivot"))
    else:
        conditions.append((_state(supply, "needs_chart") == "pass", "chart-confirmed supply absorption"))

    for satisfied, debt in conditions:
        if not satisfied:
            _add_debt(entry, debt)
    entry["state"] = "pass" if all(satisfied for satisfied, _ in conditions) else "wait"
    entry["price"] = round(close, 4)
    return entry


def build_setup_evidence(
    history: pd.DataFrame,
    *,
    chart_judgments: Mapping[str, Any] | None = None,
    tactic_opt_in: bool = False,
) -> dict[str, Any]:
    """Build only the Mapping consumed by :func:`setup.evaluate_setup`.

    Daily OHLCV supplies bounded observations and a candidate pivot. Visual
    pattern geometry, supply absorption, and named entry tactics remain caller
    judgments, so neither a VCP label nor a single computed price level can
    declare a setup complete.
    """
    bars = _completed_bars(history)
    if bars is None:
        return _unavailable_evidence("completed daily OHLCV is missing or invalid")

    judgments = _copy_mapping(chart_judgments)
    geometry = _chart_claim(judgments.get("price_geometry"))
    supply = _chart_claim(judgments.get("supply_evidence"))
    if "supply_evidence" not in judgments:
        supply.update(_volume_observation(bars))

    candidate = _candidate_pivot(bars)
    close = float(bars["Close"].iloc[-1]) if candidate is not None else None
    entry = _entry_evidence(
        judgments.get("entry"),
        candidate_pivot=candidate,
        close=close,
        geometry=geometry,
        supply=supply,
        tactic_opt_in=tactic_opt_in is True,
    )
    return {
        "price_geometry": geometry,
        "supply_evidence": supply,
        "entry": entry,
        "vcp_label": judgments.get("vcp_label"),
    }


__all__ = ["build_setup_evidence"]
