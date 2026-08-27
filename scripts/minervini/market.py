"""Pure market-evidence evaluation and candidate-universe filtering.

Providers normalize facts before they reach this module.  This module preserves
those facts as a signal vector; it deliberately does not manufacture a weighted
market score or turn an index switch into a risk-on authorization.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from . import doctrine


_LEADING_GROUP_COUNT = "market.industry_groups_leading_bull_count"
# What the harness measures against doctrine, and what only stands beside it. The order is the
# order both lists are published in.
_VERDICT_SIGNALS = ("leader_traction", "trade_traction")
_CONTEXT_SIGNALS = ("qqq_21ema_switch", "market_breadth")
_SIGNAL_STATES = frozenset(
    {
        "supports",
        "contradicts",
        "mixed",
        "observed",
        "unavailable",
        "needs_input",
        "needs_chart",
        "not_applicable",
    }
)
_POSITIVE = frozenset({"on", "positive", "constructive", "favorable", "pass", "passed", "supports"})
_NEGATIVE = frozenset({"off", "negative", "destructive", "unfavorable", "fail", "failed", "contradicts"})
_GROUP_READINGS = ("new_highs", "striking_distance_names")
_GROUP_RANK_BASIS = (*_GROUP_READINGS, "new_high_count", "provider_source_rank_tiebreaker")
_US_EXCHANGES = frozenset({"NASDAQ", "NYSE", "NYSEAMERICAN", "NYSE ARCA", "CBOE", "IEX", "MEMX"})
_ELIGIBLE_TYPES = frozenset({"common", "common_stock", "common stock", "adr"})


def evaluate_market_snapshot(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Return a transparent market-regime read from normalized provider evidence.

    A favorable judgment needs convergent breadth, QQQ context, leader behavior,
    and actual user trade traction.  The QQQ 21-EMA switch is only one signal.
    """
    if not isinstance(evidence, Mapping):
        raise ValueError("market evidence must be a mapping")

    missing: list[dict[str, str]] = []
    vector: list[dict[str, Any]] = []

    breadth = evidence.get("breadth")
    vector.append(_signal("market_breadth", breadth, missing, "breadth"))

    qqq = evidence.get("qqq_21ema")
    vector.append(_signal("qqq_21ema_switch", qqq, missing, "qqq_21ema"))

    leaders = evidence.get("leaders")
    leader_signal = _leader_signal(leaders, missing)
    vector.append(leader_signal)

    traction = evidence.get("trade_traction")
    vector.append(_signal("trade_traction", traction, missing, "trade_traction"))

    sector_ranks = _rank_groups(evidence.get("sectors"), "sector", missing)
    industry_ranks = _rank_groups(evidence.get("industries"), "industry", missing)
    vector.extend(_group_summary_signal("sector_leadership", sector_ranks))
    vector.extend(_group_summary_signal("industry_leadership", industry_ranks))

    by_id = {signal["id"]: signal["state"] for signal in vector}
    judgment = _regime_judgment(by_id)
    quality = _evidence_quality(vector, missing)
    return {
        "regime": {
            "judgment": judgment,
            "evidence": [_regime_row(vector, identifier) for identifier in _VERDICT_SIGNALS],
            "context": [_regime_row(vector, identifier) for identifier in _CONTEXT_SIGNALS],
            "qqq_switch_is_context_only": True,
            # Finviz publishes only a live page, so breadth is a current
            # observation standing in for the completed session, never a
            # measurement taken at its close.
            "breadth_is_context_only": True,
        },
        "signal_vector": vector,
        "group_ranks": {"sectors": sector_ranks, "industries": industry_ranks},
        "evidence_quality": quality,
        "missing": missing,
    }


def build_market_candidates(
    instruments: Iterable[Mapping[str, Any]], *, limit: int = 50, cursor: str | None = None
) -> dict[str, Any]:
    """Filter a security-master universe and paginate it without selecting a quota.

    ``recommendation_state`` is optional upstream judgment.  It is counted across
    the complete filtered universe, never set by this function and never capped
    by the page size.
    """
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ValueError("limit must be a positive integer")
    offset = _cursor_offset(cursor)

    eligible: dict[str, dict[str, Any]] = {}
    exclusion_total = 0
    exclusion_counts: dict[str, int] = {}
    exclusion_samples: list[dict[str, Any]] = []
    sample_limit = min(limit, 20)
    for row in instruments:
        if not isinstance(row, Mapping):
            reasons = ["invalid_instrument_record"]
            exclusion_total += 1
            exclusion_counts[reasons[0]] = exclusion_counts.get(reasons[0], 0) + 1
            if len(exclusion_samples) < sample_limit:
                exclusion_samples.append({"instrument_id": None, "ticker": None, "reasons": reasons})
            continue
        reasons = _exclusion_reasons(row)
        instrument_id = row.get("instrument_id")
        ticker = row.get("ticker")
        if not instrument_id:
            reasons.append("missing_instrument_id")
        if reasons:
            unique_reasons = _unique(reasons)
            exclusion_total += 1
            for reason in unique_reasons:
                exclusion_counts[reason] = exclusion_counts.get(reason, 0) + 1
            if len(exclusion_samples) < sample_limit:
                exclusion_samples.append({"instrument_id": instrument_id, "ticker": ticker, "reasons": unique_reasons})
            continue

        key = str(instrument_id)
        if key not in eligible:
            eligible[key] = _candidate_record(row)
        else:
            eligible[key]["origins"] = _unique(eligible[key]["origins"] + _origins(row))

    universe = list(eligible.values())
    page = universe[offset : offset + limit]
    next_offset = offset + len(page)
    next_cursor = f"offset:{next_offset}" if next_offset < len(universe) else None
    recommendation_count = sum(item["recommendation_state"] == "recommended" for item in universe)
    return {
        "candidates": page,
        "exclusions": {
            "total_count": exclusion_total,
            "reason_counts": dict(sorted(exclusion_counts.items())),
            "samples": exclusion_samples,
            "sample_limit": sample_limit,
        },
        "page": {
            "page_size": limit,
            "cursor": cursor,
            "next_cursor": next_cursor,
            "returned_count": len(page),
            "candidate_count": len(universe),
            "recommendation_count": recommendation_count,
            "exclusion_count": exclusion_total,
        },
    }


def _signal(identifier: str, value: Any, missing: list[dict[str, str]], missing_id: str) -> dict[str, Any]:
    if value is None:
        missing.append({"id": missing_id, "reason": "provider_evidence_missing"})
        return {"id": identifier, "state": "unavailable", "value": None}
    return {"id": identifier, "state": _state(value), "value": value}


def _leader_signal(leaders: Any, missing: list[dict[str, str]]) -> dict[str, Any]:
    if not isinstance(leaders, list) or not leaders:
        missing.append({"id": "leaders", "reason": "leader_evidence_missing"})
        return {"id": "leader_traction", "state": "unavailable", "value": leaders}
    states = [_state(item.get("behavior") if isinstance(item, Mapping) else None) for item in leaders]
    return {"id": "leader_traction", "state": _aggregate_states(states), "value": leaders}


def _rank_groups(groups: Any, group_type: str, missing: list[dict[str, str]]) -> list[dict[str, Any]]:
    missing_id = "industries" if group_type == "industry" else f"{group_type}s"
    if groups is None:
        missing.append({"id": missing_id, "reason": "provider_evidence_missing"})
        return []
    if not isinstance(groups, list):
        missing.append({"id": missing_id, "reason": "invalid_provider_shape"})
        return []

    ranked: list[dict[str, Any]] = []
    for index, group in enumerate(groups):
        if not isinstance(group, Mapping):
            continue
        name = group.get("name") or group.get("id") or f"{group_type}-{index + 1}"
        signals = [{"metric": metric, "state": _state(group.get(metric)), "value": group.get(metric)} for metric in _GROUP_READINGS]
        source_basis = dict(group["basis"]) if isinstance(group.get("basis"), Mapping) else {}
        ranked.append(
            {
                "name": name,
                "signal_vector": signals,
                "member_sample": group.get("member_sample"),
                "source_basis": source_basis,
                "rank_basis": list(_GROUP_RANK_BASIS),
            }
        )

    ranked.sort(key=_group_rank_key)
    for rank, group in enumerate(ranked, start=1):
        group["rank"] = rank
    return ranked


def _group_summary_signal(identifier: str, ranks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """How many groups show the advance signal, and which one ranks first.

    The count is read against the range the source gave for how many groups lead a new bull
    market, and a range cannot decide, so this signal reports and never supports. Reading only
    the top-ranked group's own states -- what this replaces -- called the whole market's group
    leadership by one row of a list the same function had just sorted.
    """

    if not ranks:
        return [{"id": identifier, "state": "unavailable", "value": []}]
    advancing = [group["name"] for group in ranks if _reading_state(group, "new_highs") == "supports"]
    read = [group for group in ranks if _reading_state(group, "new_highs") != "unavailable"]
    if not read:
        return [{"id": identifier, "state": "unavailable", "value": {"leading_group": ranks[0]["name"], "reason": "no_group_reading_available"}}]
    return [
        {
            "id": identifier,
            "state": "observed",
            "value": {
                "leading_group": ranks[0]["name"],
                "groups_showing_a_group_advance": advancing,
                "count": doctrine.evaluate_band(_LEADING_GROUP_COUNT, "leading_industry_group_count", len(advancing)),
                "of_groups_read": len(read),
            },
        }
    ]


def _reading_state(group: Mapping[str, Any], metric: str) -> str:
    return next((item["state"] for item in group["signal_vector"] if item["metric"] == metric), "unavailable")


def _regime_judgment(states: Mapping[str, str]) -> str:
    """The regime word, from the signals the harness measures against doctrine.

    Two signals can carry it: the ranked leaders read from their own bars, and the trader's
    own realized traction. The index switch is a real measurement and refuses a favorable
    call when it has gone off, but a practice-layer switch does not authorize one on its own.
    Breadth is scraped from a live page against no registered threshold, so it never gates --
    a gap there is reported by evidence quality, which is where completeness belongs.
    """

    if all(states.get(identifier) == "supports" for identifier in _VERDICT_SIGNALS):
        return "favorable" if states.get("qqq_21ema_switch") != "contradicts" else "cautious"
    if states.get("trade_traction") == "contradicts" and (
        states.get("leader_traction") == "contradicts" or states.get("qqq_21ema_switch") == "contradicts"
    ):
        return "defensive"
    if any(states.get(identifier) in {"unavailable", "needs_input", None} for identifier in _VERDICT_SIGNALS):
        return "incomplete"
    return "cautious"


def _regime_row(vector: list[dict[str, Any]], identifier: str) -> dict[str, Any]:
    state = next((signal["state"] for signal in vector if signal["id"] == identifier), "unavailable")
    return {"signal_id": identifier, "state": state}


def _evidence_quality(vector: list[dict[str, Any]], missing: list[dict[str, str]]) -> dict[str, Any]:
    core = {*_VERDICT_SIGNALS, *_CONTEXT_SIGNALS}
    core_states = {signal["id"]: signal["state"] for signal in vector if signal["id"] in core}
    if not core_states or all(state == "unavailable" for state in core_states.values()):
        status = "insufficient"
    elif missing or any(state == "unavailable" for state in core_states.values()):
        status = "partial"
    else:
        status = "complete"
    return {"status": status, "missing_ids": [item["id"] for item in missing]}


def _state(value: Any) -> str:
    if isinstance(value, Mapping):
        value = value.get("state")
    if value is None:
        return "unavailable"
    if isinstance(value, bool):
        return "supports" if value else "contradicts"
    normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in _SIGNAL_STATES:
        return normalized
    if normalized in _POSITIVE:
        return "supports"
    if normalized in _NEGATIVE:
        return "contradicts"
    return "observed"


def _aggregate_states(states: list[str]) -> str:
    non_missing = [state for state in states if state != "unavailable"]
    if not non_missing:
        return "unavailable"
    if all(state == "supports" for state in non_missing):
        return "supports"
    if all(state == "contradicts" for state in non_missing):
        return "contradicts"
    return "mixed"


def _group_rank_key(group: Mapping[str, Any]) -> tuple[Any, ...]:
    order = {"supports": 0, "observed": 1, "mixed": 2, "not_applicable": 3, "needs_chart": 4, "unavailable": 5, "needs_input": 6, "contradicts": 7}
    states = tuple(order[item["state"]] for item in group["signal_vector"])
    measured = next((item["value"] for item in group["signal_vector"] if item["metric"] == "new_highs"), None)
    now = measured.get("measured", {}).get("now") if isinstance(measured, Mapping) else None
    stage_tiebreak = -now if isinstance(now, (int, float)) and not isinstance(now, bool) else 0
    source_rank = group.get("source_basis", {}).get("rank")
    source_tiebreak = source_rank if isinstance(source_rank, (int, float)) and not isinstance(source_rank, bool) else float("inf")
    return (*states, stage_tiebreak, source_tiebreak, str(group["name"]))


def _exclusion_reasons(row: Mapping[str, Any]) -> list[str]:
    instrument_type = str(row.get("instrument_type", row.get("security_type", ""))).strip().lower()
    exchange = str(row.get("exchange", "")).strip().upper()
    listing_country = str(row.get("listing_country", "")).strip().upper()
    reasons: list[str] = []
    if instrument_type in {"etf", "fund", "exchange_traded_fund"} or row.get("is_etf"):
        reasons.append("etf_context_only")
    if instrument_type in {"spac", "blank_check"} or row.get("is_spac"):
        reasons.append("spac")
    if row.get("is_shell") or instrument_type == "shell":
        reasons.append("shell_company")
    if exchange.startswith("OTC") or row.get("is_otc"):
        reasons.append("otc")
    if listing_country != "US":
        reasons.append("non_us_listing")
    if exchange not in _US_EXCHANGES:
        reasons.append("unsupported_exchange")
    excluded_type = instrument_type in {"etf", "fund", "exchange_traded_fund", "spac", "blank_check", "shell"}
    is_adr = bool(row.get("is_adr")) or instrument_type == "adr"
    if instrument_type not in _ELIGIBLE_TYPES and not is_adr and not excluded_type:
        reasons.append("unsupported_instrument_type")
    return reasons


def _candidate_record(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "instrument_id": row["instrument_id"],
        "ticker": row.get("ticker"),
        "exchange": row.get("exchange"),
        "instrument_type": row.get("instrument_type", row.get("security_type")),
        "is_adr": bool(row.get("is_adr")) or str(row.get("instrument_type", "")).lower() == "adr",
        "origins": _origins(row),
        "recommendation_state": row.get("recommendation_state", "not_recommended"),
    }


def _origins(row: Mapping[str, Any]) -> list[str]:
    value = row.get("origins", row.get("origin", []))
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable) and not isinstance(value, Mapping):
        return _unique(str(item) for item in value)
    return []


def _cursor_offset(cursor: str | None) -> int:
    if cursor is None:
        return 0
    if not isinstance(cursor, str) or not cursor.startswith("offset:"):
        raise ValueError("cursor must use the offset:<non-negative integer> form")
    try:
        offset = int(cursor.removeprefix("offset:"))
    except ValueError as error:
        raise ValueError("cursor must use the offset:<non-negative integer> form") from error
    if offset < 0:
        raise ValueError("cursor must use the offset:<non-negative integer> form")
    return offset


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))
