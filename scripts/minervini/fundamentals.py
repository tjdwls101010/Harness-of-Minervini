"""Point-in-time filed-fundamentals evaluator.

The public evaluator deliberately accepts only normalized SEC filed facts and
optional FMP enrichment. Narrative is not a numeric evidence input.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping

from . import doctrine


_EARNINGS_QUALITY = "fundamentals.inventory_receivables_vs_sales"
_MINIMUM_GROWTH = "fundamentals.minimum_quarterly_earnings_growth"
_SUPERPERFORMANCE = "fundamentals.superperformance_quarterly_earnings_growth"
_BULL_MARKET = "fundamentals.bull_market_quarterly_earnings_growth"
_DECELERATION = "fundamentals.earnings_deceleration_red_flag"
_SMOOTHING = "fundamentals.two_quarter_rolling_average_smoothing"
_ANNUAL_REQUIREMENT = "fundamentals.annual_earnings_requirement"
_MARGIN_ANALYSIS = "fundamentals.margin_analysis"
MARKET_REGIMES = ("bull", "neutral", "bear")
_REPORTED_PRECISION = 10


SEC_SOURCE = "sec_filed_facts"
FMP_SOURCE = "fmp_enrichment"


# What an analyst may hand in beside the filings, because the filings do not carry it. The
# going-concern opinion and the audit's integrity finding live in the filing's narrative,
# which this harness does not read; the classification is a reading of the company's place
# in its industry, which no filing states at all.
GOING_CONCERN_WORDS = ("clear", "substantial_doubt")
ACCOUNTING_INTEGRITY_WORDS = ("clear", "concern", "restatement", "adverse")
LEADER_CATEGORIES = ("market_leader", "top_competitor", "institutional_favorite", "turnaround", "cyclical", "past_leader_or_laggard")


def evaluate_fundamentals(
    sec_filed_facts: Mapping[str, Any],
    *,
    as_of: str,
    fmp_enrichment: Mapping[str, Any] | None = None,
    going_concern: str | None = None,
    accounting_integrity: str | None = None,
    leader_category: str | None = None,
    market_regime: str | None = None,
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
    integrity, safety_missing = _integrity_read(quarters, going_concern=going_concern, accounting_integrity=accounting_integrity)
    earnings_quality = {"inventory_receivables_vs_sales": _inventory_receivables_vs_sales(annual)}
    growth = _growth_read(quarterly, market_regime=market_regime)
    classification = _leader_category(leader_category)
    growth_quality, growth_missing = _growth_quality(growth, quarterly, annual_growth)
    discrepancies = _fmp_discrepancies(quarters, fmp_enrichment, as_of_date)

    # The classification is not counted here. A reading the harness never derives is a
    # boundary of what this capability does, published once in its limitations, and turning
    # it into a per-request gap says the filings were short of something they never held.
    missing = [*safety_missing, *growth_missing]
    fundamentals_state = _fundamentals_state(
        integrity=integrity,
        growth_quality=growth_quality,
        safety_missing=safety_missing,
        growth_missing=growth_missing,
    )

    return {
        "as_of": as_of_date.isoformat(),
        "filings_used": [filing["filed_at"] for filing in filings],
        # Which of those filings restated numbers that had already been published. It is
        # provenance rather than a finding: no source in this harness's corpus says an
        # amendment is evidence about the company, so it changes no verdict and is put in
        # front of a reader who may want to know the figures moved after the fact.
        "amended_filings": [
            {"filed_at": filing["filed_at"], "form": filing["form"]}
            for filing in filings
            if isinstance(filing.get("form"), str) and filing["form"].endswith("/A")
        ],
        "accounting_basis": basis,
        "quarterly": quarterly,
        "growth": growth,
        "annual_growth": annual_growth,
        "quality": growth_quality,
        "integrity": integrity,
        "earnings_quality": earnings_quality,
        "leader_category": classification,
        "discrepancies": discrepancies,
        "signals": [
            {"id": name, "state": item["state"]}
            for name, item in {**integrity, "quality": growth_quality}.items()
        ],
        "declared_inputs": {"going_concern": going_concern, "accounting_integrity": accounting_integrity, "leader_category": leader_category},
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
            margin.append(_point(quarter, _reported(float(income) / float(sales) * 100)))
    return {
        "eps": eps,
        "revenue": revenue,
        "margin_pct": margin,
        "eps_yoy_growth": _yoy_growth(eps),
        "revenue_yoy_growth": _yoy_growth(revenue),
    }


def _yoy_growth(series: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each quarter against the same quarter a year earlier, which is the comparison the source makes.

    Quarter on quarter would report a seasonal business as accelerating and decelerating on
    a calendar rather than on its own progress.
    """

    year_ago = {point["period"]: point["value"] for point in series}
    growth = []
    for point in series:
        previous = year_ago.get(_previous_year_quarter(point["period"]))
        if previous not in (None, 0):
            growth.append({"period": point["period"], "yoy_pct": _reported((point["value"] / previous - 1) * 100)})
    return growth


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




def _previous_year_quarter(period: str) -> str:
    if "-Q" not in period:
        return ""
    year, quarter = period.rsplit("-Q", 1)
    try:
        return f"{int(year) - 1}-Q{quarter}"
    except ValueError:
        return ""



def _annual_growth(annual: list[dict[str, Any]]) -> dict[str, Any]:
    """Annual earnings and sales growth, reported against a requirement nobody quantified.

    The claim is a constitution-level one -- quarterly strength has to translate into annual
    results, a quarter or two being insufficient -- and it is registered judgment_only with
    no threshold, because the source never says how strong. What used to be here compared
    the annual rise against twenty percent, a number the source stated about quarters.
    """

    return {
        "doctrine_id": _ANNUAL_REQUIREMENT,
        "binds": doctrine.binds(_ANNUAL_REQUIREMENT),
        "computability": doctrine.get_claim(_ANNUAL_REQUIREMENT)["claim"]["computability"],
        "periods": [fact.get("period") for fact in annual[-2:]],
        "eps_yoy_pct": _annual_metric_growth(annual, "eps"),
        "revenue_yoy_pct": _annual_metric_growth(annual, "revenue"),
    }


def _annual_metric_growth(annual: list[dict[str, Any]], metric: str) -> float | None:
    values = [float(fact[metric]) for fact in annual if _is_number(fact.get(metric))]
    if len(values) < 2 or values[-2] == 0:
        return None
    return _reported((values[-1] / values[-2] - 1) * 100)


def _integrity_read(quarters: list[dict[str, Any]], *, going_concern: str | None, accounting_integrity: str | None) -> tuple[dict[str, Any], list[str]]:
    """What the filed numbers can say about earnings quality, and what only a reader can.

    Two of these are narrative. The auditor's going-concern opinion and its integrity
    findings are prose in the filing, and this harness reads filed numeric facts. So they
    are not asked of the filings: with nothing declared they report the boundary they sit
    outside of, and a declaration by someone who did read the filing is honoured.

    Only what was actually measured can be missing. Dilution is computed from the filed
    share counts, so an absent count is a real gap about this company.
    """

    accounting = _declared_status(accounting_integrity, allowed=ACCOUNTING_INTEGRITY_WORDS, critical_terms={"concern", "restatement", "adverse"})
    concern = _declared_status(going_concern, allowed=GOING_CONCERN_WORDS, critical_terms={"substantial_doubt"})
    return {"accounting_integrity": accounting, "going_concern": concern, "dilution": _dilution_reading(quarters)}, []


def _declared_status(value: Any, *, allowed: tuple[str, ...], critical_terms: set[str]) -> dict[str, Any]:
    if value is None:
        return {"state": "not_evaluated", "reason": "narrative_disclosure_not_read_by_this_harness"}
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"declared status must be one of {', '.join(allowed)}.")
    if value in critical_terms:
        return {"state": "contradicts", "declared_status": value}
    return {"state": "supports", "declared_status": value}


def _dilution_reading(quarters: list[dict[str, Any]]) -> dict[str, Any]:
    """How the diluted share count moved between the two latest filed quarters.

    Reported, never judged. This used to call a ten-percent quarterly rise a contradiction
    and reject a candidate on it, but neither corpus this harness reads mentions dilution --
    the word does not appear once in either -- so the limit was the harness's own opinion
    wearing the shape of doctrine. The count is a filed fact and belongs in front of a
    reader; deciding what it means about the company is the reader's, until a source says
    otherwise and the registry carries the quotation.
    """

    if len(quarters) < 2 or not _is_number(quarters[-1].get("diluted_shares")) or not _is_number(quarters[-2].get("diluted_shares")):
        return {"state": "unavailable", "reason": "two_filed_share_counts_required"}
    previous, current = float(quarters[-2]["diluted_shares"]), float(quarters[-1]["diluted_shares"])
    if previous <= 0:
        return {"state": "unavailable", "reason": "share_count_is_not_a_count"}
    return {
        "state": "reported",
        "periods": [quarters[-2].get("period"), quarters[-1].get("period")],
        "quarterly_share_change_pct": _reported((current / previous - 1) * 100),
    }


def _growth_read(quarterly: Mapping[str, Any], *, market_regime: str | None) -> dict[str, Any]:
    """The latest year-over-year quarterly growth, against the ranges the source named.

    Ranges, not limits. "Many successful growth managers require a minimum of 20 to 25
    percent" is a range the source gave as a range, so each reading says where the
    measurement sat and which edge is the good one, and none of them carries a verdict
    alone -- every fundamentals claim in the registry prompts review rather than deciding.

    Three bars are read from one number because they are three different ambitions for the
    same measurement: a minimum a growth manager would accept, the pace that shows up in
    superperformance, and what the source looks for in a bull market. Only the last needs
    the regime declared, so only the last can go unread for want of it.
    """

    series = quarterly["eps_yoy_growth"]
    latest = series[-1]["yoy_pct"] if series else None
    readings = {
        "minimum_quarterly_earnings_growth": doctrine.evaluate_band(_MINIMUM_GROWTH, "minimum_yoy_earnings_growth_percent", latest),
        "superperformance_quarterly_earnings_growth": doctrine.evaluate_band(_SUPERPERFORMANCE, "superperformance_yoy_earnings_growth_percent", latest),
        "bull_market_quarterly_earnings_growth": _bull_market_read(latest, market_regime),
        "earnings_deceleration": _deceleration_read(series),
        "two_quarter_rolling_average": _rolling_average(quarterly),
        "margin_trend": _margin_read(quarterly["margin_pct"]),
    }
    return readings


def _margin_read(series: list[dict[str, Any]]) -> dict[str, Any]:
    """How the net margin moved between the two latest filed quarters.

    Reported, not endorsed. This used to call any rise `supports` and any fall
    `contradicts`, which made a margin one hundredth of a point better than last quarter an
    argument for the trade. The claim it belongs to asks for an industry average this
    harness has no source for, so that input is named as unread rather than worked around.
    """

    reading = {
        "doctrine_id": _MARGIN_ANALYSIS,
        "binds": doctrine.binds(_MARGIN_ANALYSIS),
        "missing_inputs": ["industry_avg_net_margin"],
    }
    if len(series) < 2:
        return {**reading, "reason": "two_filed_quarters_required", "latest_change_pct_points": None}
    return {
        **reading,
        "periods": [series[-2]["period"], series[-1]["period"]],
        "latest_net_margin_pct": series[-1]["value"],
        "latest_change_pct_points": _reported(series[-1]["value"] - series[-2]["value"]),
    }


def _bull_market_read(latest: float | None, market_regime: str | None) -> dict[str, Any]:
    """The bull-market pace, which the claim asks for a regime classification to read at all."""

    if market_regime is None:
        return {"doctrine_id": _BULL_MARKET, "state": "unavailable", "missing_inputs": ["market_regime_classification"]}
    if market_regime not in MARKET_REGIMES:
        raise ValueError(f"market_regime must be one of {', '.join(MARKET_REGIMES)}.")
    if market_regime != "bull":
        return {"doctrine_id": _BULL_MARKET, "state": "not_applicable", "market_regime": market_regime}
    return {**doctrine.evaluate_band(_BULL_MARKET, "bull_market_yoy_earnings_growth_percent", latest), "market_regime": market_regime}


def _deceleration_read(series: list[dict[str, Any]]) -> dict[str, Any]:
    """Whether the latest growth rate came in under the one before it.

    The source illustrated the shape with sixty percent falling to twenty-five, and the
    registry records both figures as references, which are never compared with a ticker's
    measurement at all -- they describe the shape the source was pointing at. So this
    publishes the two rates and whether the later one was lower, and nothing that reads as a
    limit having been crossed. How much of a slowdown matters is a judgement the source
    declined to bound, and inventing one here is how the previous reading came to reject a
    candidate whose growth fell fifteen points from its own recent peak.
    """

    if len(series) < 2:
        return {"doctrine_id": _DECELERATION, "reason": "two_year_over_year_rates_required", "latest_yoy_pct": series[-1]["yoy_pct"] if series else None, "previous_yoy_pct": None, "decelerated": None}
    latest, previous = series[-1]["yoy_pct"], series[-2]["yoy_pct"]
    return {
        "doctrine_id": _DECELERATION,
        "binds": doctrine.binds(_DECELERATION),
        "periods": [series[-2]["period"], series[-1]["period"]],
        "latest_yoy_pct": latest,
        "previous_yoy_pct": previous,
        "change_pct_points": _reported(latest - previous),
        "decelerated": latest < previous,
    }


def _rolling_average(quarterly: Mapping[str, Any]) -> dict[str, Any]:
    """Two quarters averaged, the way the tactic smooths a lumpy pair.

    It travels beside the raw rate rather than replacing it: a practice-layer tactic does not
    bind, and a reader deciding on the smoothed number should be able to see the two it came
    from.
    """

    window = int(doctrine.threshold(_SMOOTHING, "rolling_average_window_quarters"))
    averages = {}
    for name in ("eps", "revenue"):
        series = quarterly[f"{name}_yoy_growth"]
        averages[f"{name}_yoy_pct"] = _reported(sum(point["yoy_pct"] for point in series[-window:]) / window) if len(series) >= window else None
    return {
        "doctrine_id": _SMOOTHING,
        "binds": doctrine.binds(_SMOOTHING),
        "window_quarters": window,
        **averages,
    }


def _inventory_receivables_vs_sales(annual: list[dict[str, Any]]) -> dict[str, Any]:
    """Whether the balance sheet grew the way sales did.

    Inventory is merchandise waiting to be sold, so under most conditions it should rise and
    fall with sales; the same is true of what customers still owe. Both running at twice the
    sales rate, unexplained, is the source's "double trouble" -- earnings the balance sheet
    has not been paid for yet, sitting beside goods nobody bought.

    It reads what the filings hold, which is why it is here at all: the accounting-integrity
    verdict this used to publish was read from a field the provider never sent. It is an
    interpretation, so the finding prompts review and never decides the verdict on its own.
    """

    if len(annual) < 2:
        return {"doctrine_id": _EARNINGS_QUALITY, "state": "unavailable", "reason": "two_annual_periods_required"}
    previous, latest = annual[-2], annual[-1]
    missing = [name for name in ("accounts_receivable", "inventory") if not (_is_number(previous.get(name)) and _is_number(latest.get(name)))]
    if not (_is_number(previous.get("revenue")) and _is_number(latest.get("revenue"))):
        missing.append("revenue")
    reading: dict[str, Any] = {
        "doctrine_id": _EARNINGS_QUALITY,
        "binds": doctrine.binds(_EARNINGS_QUALITY),
        "periods": [previous.get("period"), latest.get("period")],
        "revenue_growth_pct": _growth_pct(previous.get("revenue"), latest.get("revenue")),
        "accounts_receivable_growth_pct": _growth_pct(previous.get("accounts_receivable"), latest.get("accounts_receivable")),
        "inventory_growth_pct": _growth_pct(previous.get("inventory"), latest.get("inventory")),
    }
    if missing:
        # A company with no inventory concept in its filings has no inventory, and one whose
        # filings simply omit it looks identical from here. Either way this reading did not
        # happen, and it says so rather than being counted as a gap the company left.
        return {**reading, "state": "unavailable", "missing_inputs": missing}
    sales_growth = reading["revenue_growth_pct"]
    if sales_growth is None or sales_growth <= 0:
        # The comparison the source states is "growing at a greater rate than sales". Against
        # sales that did not grow there is no such rate: dividing a rise by a fall returns a
        # negative number, which would then read as comfortably inside a limit of two.
        return {**reading, "state": "sales_did_not_grow", "inventory_vs_sales_ratio": None, "accounts_receivable_vs_sales_ratio": None}
    ratios = {
        f"{name}_vs_sales_ratio": _reported(reading[f"{name}_growth_pct"] / sales_growth) if reading[f"{name}_growth_pct"] is not None else None
        for name in ("inventory", "accounts_receivable")
    }
    both = [ratios["inventory_vs_sales_ratio"], ratios["accounts_receivable_vs_sales_ratio"]]
    # The source's finding is about both at once: one line running ahead of sales has an
    # ordinary explanation far more often than two do.
    gates = {name: doctrine.evaluate_gate(_EARNINGS_QUALITY, "receivables_and_inventory_vs_sales_double_trouble_ratio", value) for name, value in ratios.items()}
    doubled = all(value is not None and gate["state"] == "fail" for value, gate in zip(both, gates.values()))
    return {**reading, **ratios, "state": "double_trouble" if doubled else "reported", "gates": gates}


def _growth_pct(previous: Any, latest: Any) -> float | None:
    if not (_is_number(previous) and _is_number(latest)) or float(previous) <= 0:
        return None
    return _reported((float(latest) / float(previous) - 1) * 100)


def _reported(value: float | None) -> float | None:
    return None if value is None else round(value, _REPORTED_PRECISION)


def _leader_category(declared: str | None) -> dict[str, Any]:
    """The company's place among its peers, which the analyst declares and no filing states.

    It used to be read from the filing mapping, which meant it was read from nothing: the
    provider has never sent such a field. What it is for is interpretation -- the same
    earnings history reads differently for a market leader and for a turnaround -- so it
    travels with the reading rather than deciding it.
    """

    if declared is None:
        return {"state": "not_declared", "category": None}
    if declared not in LEADER_CATEGORIES:
        raise ValueError(f"leader_category must be one of {', '.join(LEADER_CATEGORIES)}.")
    return {"state": "declared", "category": declared}


def _growth_quality(growth: Mapping[str, Any], quarterly: Mapping[str, Any], annual: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Whether the filed growth supports convergence, read from the band beside it.

    One owner. This used to answer the question a second time, from slowdown thresholds that
    appear in neither corpus -- fifteen points off a stock's own recent peak was a
    contradiction, five was mixed -- and a reader comparing the verdict with the readings
    published next to it could find them disagreeing.

    The band that decides is the minimum the source names, because that is what it is: "many
    successful growth managers require a minimum of 20 to 25 percent". Inside that range is
    at the minimum and supports; short of it does not. The higher bars are read from the same
    number and reported as context, since a candidate can support convergence without being
    a superperformer.
    """

    missing = []
    if not quarterly["eps"]:
        missing.append("quarterly_eps")
    if not quarterly["revenue"]:
        missing.append("quarterly_revenue")
    if not quarterly["eps_yoy_growth"]:
        # No quarter with the same quarter a year earlier beside it. Growth against the
        # previous quarter would report a seasonal business on a calendar rather than on its
        # own progress, so there is nothing to read instead.
        missing.append("quarterly_eps_yoy_growth")
    if annual["eps_yoy_pct"] is None or annual["revenue_yoy_pct"] is None:
        missing.append("annual_growth")
    minimum = growth["minimum_quarterly_earnings_growth"]
    if missing or minimum["state"] == "unavailable":
        return {"state": "unavailable", "minimum_growth_state": minimum["state"]}, missing
    return {
        "state": "supports" if minimum["state"] in {"within_source_range", "above_source_range"} else "contradicts",
        "minimum_growth_state": minimum["state"],
        "measured_yoy_pct": minimum["measured"],
        "decided_by": _MINIMUM_GROWTH,
    }, missing


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
                discrepancies.append({"period": sec["period"], "metric": metric, "sec_value": float(sec[metric]), "fmp_value": float(fmp[metric]), "delta": _reported(float(sec[metric]) - float(fmp[metric]))})
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
    # "not_evaluated" is deliberately not a gap here. It marks a check outside what this
    # capability does at all, which its limitations state once, rather than evidence this
    # company was short of.
    if safety_missing or growth_missing:
        return "incomplete"
    return "supports_convergence" if growth_quality["state"] == "supports" else "does_not_support_convergence"


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
