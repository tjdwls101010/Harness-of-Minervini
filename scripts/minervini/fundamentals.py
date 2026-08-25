"""Point-in-time filed-fundamentals evaluator.

The public evaluator deliberately accepts only normalized SEC filed facts and
optional FMP enrichment. Narrative is not a numeric evidence input.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping


SEC_SOURCE = "sec_filed_facts"
FMP_SOURCE = "fmp_enrichment"


def evaluate_fundamentals(
    sec_filed_facts: Mapping[str, Any],
    *,
    as_of: str,
    fmp_enrichment: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate normalized SEC filings available on ``as_of``.

    Each filing must identify ``filed_at`` and ``accounting_basis`` and may
    contain ``quarterly`` and ``annual`` normalized facts. Later eligible
    filings supersede earlier facts for the same period, while a filing after
    ``as_of`` is never considered. FMP values are comparison-only enrichment.
    """
    _require_source(sec_filed_facts, SEC_SOURCE, "SEC filed facts")
    as_of_date = _parse_date(as_of, "as_of")
    filings = _eligible_filings(sec_filed_facts.get("filings"), as_of_date)
    quarters = _latest_periods(filings, "quarterly")
    annual = _latest_periods(filings, "annual")
    basis = _accounting_basis(filings)

    quarterly = _quarterly_read(quarters)
    annual_growth = _annual_growth(annual)
    integrity, safety_missing = _integrity_read(filings, quarters)
    leader_category = _leader_category(filings)
    growth_quality, growth_missing = _growth_quality(quarterly, annual_growth)
    discrepancies = _fmp_discrepancies(quarters, fmp_enrichment, as_of_date)

    missing = [
        *safety_missing,
        *growth_missing,
        *( ["leader_category"] if leader_category["state"] == "unavailable" else [] ),
    ]
    fundamentals_state = _fundamentals_state(
        integrity=integrity,
        growth_quality=growth_quality,
        safety_missing=safety_missing,
        growth_missing=growth_missing,
    )

    return {
        "as_of": as_of_date.isoformat(),
        "filings_used": [filing["filed_at"] for filing in filings],
        "accounting_basis": basis,
        "quarterly": quarterly,
        "annual_growth": annual_growth,
        "quality": growth_quality,
        "integrity": integrity,
        "leader_category": leader_category,
        "discrepancies": discrepancies,
        "signals": [
            {"id": name, "state": item["state"]}
            for name, item in {**integrity, "quality": growth_quality}.items()
        ],
        "fundamentals_state": fundamentals_state,
        "missing": _dedupe(missing),
    }


def _require_source(evidence: Mapping[str, Any], expected: str, label: str) -> None:
    if evidence.get("source") != expected:
        raise ValueError(f"{label} evidence is required; web narrative cannot supply numeric facts.")


def _parse_date(value: Any, field: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date.")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO date.") from error


def _eligible_filings(value: Any, as_of: date) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("SEC filed facts must contain a filings list.")
    eligible: list[dict[str, Any]] = []
    for filing in value:
        if not isinstance(filing, Mapping):
            raise ValueError("Each SEC filing must be an object.")
        filed_at = _parse_date(filing.get("filed_at"), "filed_at")
        basis = filing.get("accounting_basis")
        if basis not in {"US-GAAP", "IFRS"}:
            raise ValueError("Each SEC filing must preserve accounting_basis as US-GAAP or IFRS.")
        if filed_at <= as_of:
            eligible.append({**filing, "filed_at": filed_at.isoformat(), "_filed_date": filed_at})
    return sorted(eligible, key=lambda filing: filing["_filed_date"])


def _latest_periods(filings: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    by_period: dict[str, dict[str, Any]] = {}
    for filing in filings:
        facts = filing.get(key, [])
        if not isinstance(facts, list):
            raise ValueError(f"SEC filing {key} must be a list.")
        for fact in facts:
            if not isinstance(fact, Mapping) or not isinstance(fact.get("period"), str):
                raise ValueError(f"Each {key} fact must identify a period.")
            by_period[fact["period"]] = {**fact, "accounting_basis": filing["accounting_basis"], "filed_at": filing["filed_at"]}
    return [by_period[period] for period in sorted(by_period, key=lambda period: _period_sort_key(by_period[period]))]


def _period_sort_key(fact: Mapping[str, Any]) -> tuple[str, str]:
    return (str(fact.get("end", "")), str(fact["period"]))


def _accounting_basis(filings: list[dict[str, Any]]) -> list[str]:
    return _dedupe([str(filing["accounting_basis"]) for filing in filings])


def _quarterly_read(quarters: list[dict[str, Any]]) -> dict[str, Any]:
    eps = _metric_series(quarters, "eps")
    revenue = _metric_series(quarters, "revenue")
    margin = []
    for quarter in quarters:
        income, sales = quarter.get("net_income"), quarter.get("revenue")
        if _is_number(income) and _is_number(sales) and sales != 0:
            margin.append(_point(quarter, round(float(income) / float(sales) * 100, 2)))
    return {
        "eps": eps,
        "revenue": revenue,
        "margin_pct": margin,
        "eps_deceleration": _own_trend(eps),
        "revenue_deceleration": _own_trend(revenue),
        "margin_trend": _margin_trend(margin),
    }


def _metric_series(facts: list[dict[str, Any]], metric: str) -> list[dict[str, Any]]:
    return [_point(fact, float(fact[metric])) for fact in facts if _is_number(fact.get(metric))]


def _point(fact: Mapping[str, Any], value: float) -> dict[str, Any]:
    return {
        "period": fact["period"],
        "end": fact.get("end"),
        "value": value,
        "accounting_basis": fact["accounting_basis"],
        "filed_at": fact["filed_at"],
    }


def _own_trend(series: list[dict[str, Any]]) -> dict[str, Any]:
    year_ago = {_quarter_identity(point["period"]): point["value"] for point in series}
    growth = []
    for point in series:
        previous_period = _previous_year_quarter(point["period"])
        previous = year_ago.get(previous_period)
        if previous not in (None, 0):
            growth.append({"period": point["period"], "yoy_pct": round((point["value"] / previous - 1) * 100, 1)})
    if len(growth) < 3:
        return {"state": "unavailable", "yoy_growth": growth}
    prior_peak = max(item["yoy_pct"] for item in growth[-3:-1])
    latest = growth[-1]["yoy_pct"]
    decline = round(prior_peak - latest, 1)
    if decline >= 15:
        state = "contradicts"
    elif decline >= 5:
        state = "mixed"
    else:
        state = "supports"
    return {"state": state, "yoy_growth": growth, "slowdown_from_recent_peak_pct_points": decline}


def _quarter_identity(period: str) -> str:
    return period


def _previous_year_quarter(period: str) -> str:
    if "-Q" not in period:
        return ""
    year, quarter = period.rsplit("-Q", 1)
    try:
        return f"{int(year) - 1}-Q{quarter}"
    except ValueError:
        return ""


def _margin_trend(series: list[dict[str, Any]]) -> dict[str, Any]:
    if len(series) < 2:
        return {"state": "unavailable"}
    change = round(series[-1]["value"] - series[-2]["value"], 2)
    return {"state": "supports" if change > 0 else "contradicts" if change < 0 else "mixed", "latest_change_pct_points": change}


def _annual_growth(annual: list[dict[str, Any]]) -> dict[str, Any]:
    eps = _annual_metric_growth(annual, "eps")
    revenue = _annual_metric_growth(annual, "revenue")
    return {
        "eps_yoy_pct": eps,
        "revenue_yoy_pct": revenue,
        "state": "unavailable" if eps is None or revenue is None else "supports" if eps >= 20 and revenue > 0 else "mixed",
    }


def _annual_metric_growth(annual: list[dict[str, Any]], metric: str) -> float | None:
    values = [float(fact[metric]) for fact in annual if _is_number(fact.get(metric))]
    if len(values) < 2 or values[-2] == 0:
        return None
    return round((values[-1] / values[-2] - 1) * 100, 1)


def _integrity_read(filings: list[dict[str, Any]], quarters: list[dict[str, Any]]) -> tuple[dict[str, Any], list[str]]:
    latest = filings[-1] if filings else {}
    accounting = _safety_status(latest.get("accounting_integrity"), critical_terms={"concern", "restatement", "adverse"})
    going_concern = _safety_status(latest.get("going_concern"), critical_terms={"substantial_doubt", "concern", "adverse"})
    dilution = _dilution_status(latest, quarters)
    missing = [name for name, item in (("accounting_integrity", accounting), ("going_concern", going_concern), ("dilution", dilution)) if item["state"] == "unavailable"]
    return {"accounting_integrity": accounting, "going_concern": going_concern, "dilution": dilution}, missing


def _safety_status(value: Any, *, critical_terms: set[str]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not isinstance(value.get("status"), str):
        return {"state": "unavailable"}
    status = value["status"]
    if status == "clear":
        return {"state": "supports", "reported_status": status}
    if status in critical_terms:
        return {"state": "contradicts", "reported_status": status}
    return {"state": "unavailable", "reported_status": status}


def _dilution_status(latest_filing: Mapping[str, Any], quarters: list[dict[str, Any]]) -> dict[str, Any]:
    declared = latest_filing.get("dilution")
    if isinstance(declared, Mapping):
        return _safety_status(declared, critical_terms={"excessive", "concern"})
    if len(quarters) < 2 or not _is_number(quarters[-1].get("diluted_shares")) or not _is_number(quarters[-2].get("diluted_shares")):
        return {"state": "unavailable"}
    previous, current = float(quarters[-2]["diluted_shares"]), float(quarters[-1]["diluted_shares"])
    if previous <= 0:
        return {"state": "unavailable"}
    increase = round((current / previous - 1) * 100, 1)
    return {"state": "contradicts" if increase >= 10 else "supports", "quarterly_share_change_pct": increase}


def _leader_category(filings: list[dict[str, Any]]) -> dict[str, Any]:
    value = filings[-1].get("leader_category") if filings else None
    if not isinstance(value, Mapping) or not isinstance(value.get("category"), str):
        return {"state": "unavailable", "category": None}
    state = value.get("status") if value.get("status") in {"supports", "contradicts", "mixed"} else "unavailable"
    return {"state": state, "category": value["category"]}


def _growth_quality(quarterly: Mapping[str, Any], annual: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    missing = []
    if not quarterly["eps"]:
        missing.append("quarterly_eps")
    if not quarterly["revenue"]:
        missing.append("quarterly_revenue")
    if not quarterly["margin_pct"]:
        missing.append("quarterly_margin")
    if quarterly["eps_deceleration"]["state"] == "unavailable":
        missing.append("eps_deceleration")
    if quarterly["revenue_deceleration"]["state"] == "unavailable":
        missing.append("revenue_deceleration")
    if quarterly["margin_trend"]["state"] == "unavailable":
        missing.append("margin_trend")
    if annual["eps_yoy_pct"] is None or annual["revenue_yoy_pct"] is None:
        missing.append("annual_growth")
    if missing:
        return {"state": "unavailable"}, missing
    component_states = [quarterly["eps_deceleration"]["state"], quarterly["revenue_deceleration"]["state"], quarterly["margin_trend"]["state"], annual["state"]]
    if "contradicts" in component_states:
        state = "contradicts"
    elif "unavailable" in component_states:
        state = "mixed"
    elif "mixed" in component_states:
        state = "mixed"
    else:
        state = "supports"
    return {"state": state, "components": component_states}, missing


def _fmp_discrepancies(quarters: list[dict[str, Any]], enrichment: Mapping[str, Any] | None, as_of: date) -> list[dict[str, Any]]:
    if enrichment is None:
        return []
    _require_source(enrichment, FMP_SOURCE, "FMP enrichment")
    observed_at = _parse_date(enrichment.get("observed_at"), "FMP observed_at")
    if observed_at > as_of:
        return []
    fmp_quarters = enrichment.get("quarterly", [])
    if not isinstance(fmp_quarters, list):
        raise ValueError("FMP enrichment quarterly must be a list.")
    fmp_by_period = {fact.get("period"): fact for fact in fmp_quarters if isinstance(fact, Mapping)}
    discrepancies = []
    for sec in quarters:
        fmp = fmp_by_period.get(sec["period"])
        if not fmp:
            continue
        for metric in ("eps", "revenue"):
            if _is_number(sec.get(metric)) and _is_number(fmp.get(metric)) and float(sec[metric]) != float(fmp[metric]):
                discrepancies.append({"period": sec["period"], "metric": metric, "sec_value": float(sec[metric]), "fmp_value": float(fmp[metric]), "delta": round(float(sec[metric]) - float(fmp[metric]), 4)})
    return discrepancies


def _fundamentals_state(*, integrity: Mapping[str, Any], growth_quality: Mapping[str, Any], safety_missing: list[str], growth_missing: list[str]) -> str:
    """No branch here waives anything.

    A `power_play` argument used to arrive beside these facts and, when five of its fields said
    "pass", turned missing growth data into `waived_by_exception`. All five were the caller's
    own word about controls verified somewhere else, and nothing in the path read a price bar.
    The exception the source describes is real, but it is earned by a measured structure and an
    approved chart, and this evaluator sees neither: it holds SEC filings.

    So the gap stays a gap. What may lift it is a Power Play the harness measured itself, and
    the surface that measures one is `ticker.power-play`.
    """
    safety_states = [item["state"] for item in integrity.values()]
    if "contradicts" in safety_states:
        return "does_not_support_convergence"
    if safety_missing or growth_missing:
        return "incomplete"
    return "supports_convergence" if growth_quality["state"] == "supports" else "does_not_support_convergence"


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
