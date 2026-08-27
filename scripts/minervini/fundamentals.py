"""Point-in-time filed-fundamentals evaluator.

The public evaluator deliberately accepts only normalized SEC filed facts and
optional FMP enrichment. Narrative is not a numeric evidence input.
"""

from __future__ import annotations

from datetime import date, timedelta
import math
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
_CODE_33 = "fundamentals.code_33_triple_acceleration"
_COST_CUTTING = "fundamentals.cost_cutting_unsustainable"
_HISTORICAL_ACCELERATION = "fundamentals.earnings_acceleration_vs_historical_growth_rate"
_ONE_TIME_INCOME = "fundamentals.one_time_income_exclusion"
_HISTORY_LOOKBACK = "fundamentals.earnings_history_lookback_window"
_TURNAROUND_GROWTH = "fundamentals.turnaround_growth_rate_threshold"
_TURNAROUND_CRITERIA = "fundamentals.turnaround_qualifying_criteria"
_MARKET_LEADER = "fundamentals.market_leader_earnings_growth_pace"
_INSTITUTIONAL_FAVORITE = "fundamentals.institutional_favorite_growth_pace"
_TOP_COMPETITOR = "fundamentals.top_competitor_reading"
_LAGGARD = "fundamentals.laggard_fundamentals_reading"
_CYCLICAL = "fundamentals.cyclical_inverse_pe_and_signals"
_REPEATED_CHARGE = "fundamentals.repeated_one_time_charge_red_flag"
_TAX_DISCLOSURE = "fundamentals.tax_disclosure_red_flag"
_PE_USELESS = "fundamentals.pe_useless_alone"
_ANTI_LOW_PE = "fundamentals.anti_low_pe_bargain_trap"
_PE_EXPANSION = "fundamentals.pe_expansion_late_stage_and_historical_average"
_MONTHS_PER_YEAR = 12
_RETURN_ON_EQUITY = "practitioners.fundamentals.minervini_roe_15_to_17_or_higher"
_ANNUAL_ONLY_FORMS = ("20-F",)
_ZANGER_GROWTH = "practitioners.earnings.zanger_min_30_to_40pct_gains_each_quarter_greater"
_SEQUENTIAL_ACCELERATION = "practitioners.earnings.minervini_accelerating_1_to_4_quarters"
_RITCHIE_GROWTH = "practitioners.earnings.ritchie_not_mechanical_explosive_growth_only"
_PE_VIEWS = ("practitioners.fundamentals.minervini_pe_indifferent_prefers_high_over_ultralow", "practitioners.fundamentals.ritchie_never_pe")
# One agrees without a number and two say they never look at it. The Minervini claim records
# the disagreement as prose; naming the claims puts the sentences themselves in front of the
# reader, which is the only form in which "never" and "secondary" stay distinguishable.
_ROE_VIEWS = (
    "practitioners.fundamentals.ryan_roe_margins_important_no_number",
    "practitioners.fundamentals.zanger_never_roe_sometimes_margins",
    "practitioners.fundamentals.ritchie_never_roe_margins_secondary",
)
MARKET_REGIMES = ("bull", "neutral", "bear")
_REPORTED_PRECISION = 10
_QUARTERS_PER_YEAR = 4
_FOUR_FILED_QUARTERS = "four_consecutive_filed_quarters"
_ROLLED_FORWARD = "annual_rolled_forward_by_filed_quarters"
# Half a quarter, used to ask which calendar quarter a fiscal year's closing date belongs to:
# the quarter that ends on it is the one whose middle sits this far behind it. Not a threshold
# -- it is the same midpoint rule the SEC provider labels a duration fact by.
_HALF_QUARTER_DAYS = 365 // (2 * _QUARTERS_PER_YEAR)


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
    last_close: float | None = None,
    breakout_close: float | None = None,
    breakout_date: str | None = None,
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
    quarters, quarterly_conflicts = _merge_periods(filings, "quarterly")
    annual, annual_conflicts = _merge_periods(filings, "annual")
    identity_missing = (["quarterly_periods_two_closes_reached"] if quarterly_conflicts else []) + (["annual_periods_two_closes_reached"] if annual_conflicts else [])
    basis = _accounting_basis(filings)

    quarterly = _quarterly_read(quarters)
    annual_growth = _annual_growth(annual)
    integrity, safety_missing = _integrity_read(quarters, going_concern=going_concern, accounting_integrity=accounting_integrity)
    earnings_quality = {
        "inventory_receivables_vs_sales": _inventory_receivables_vs_sales(annual),
        "one_time_income_exclusion": _one_time_income_exclusion(),
        # Both of these live in filing prose. They are named so a reader knows the check was
        # not run, rather than discovering its absence by the silence where a finding would be.
        "repeated_one_time_charge_red_flag": _unread_claim(_REPEATED_CHARGE, ["filing_history_nonrecurring_charges"], reason="filing_footnotes_not_read_by_this_harness"),
        "tax_disclosure_red_flag": _unread_claim(_TAX_DISCLOSURE, ["filing_footnotes_tax_disclosure", "effective_tax_rate", "reported_pretax_income"], reason="filing_footnotes_not_read_by_this_harness"),
    }
    growth = _growth_read(quarterly, annual, market_regime=market_regime)
    classification = _leader_category(leader_category)
    valuation = _valuation(filings, quarterly, annual, as_of_date, last_close=last_close, breakout_close=breakout_close, breakout_date=breakout_date)
    profitability = {"return_on_equity": _return_on_equity(annual), "practitioner_views": [_practitioner_view(claim_id) for claim_id in _ROE_VIEWS]}
    category_reading = _category_reading(classification, quarterly, annual)
    growth_quality, growth_missing = _growth_quality(growth, quarterly, annual_growth)
    growth_missing = _annual_only(filings, growth_missing)
    discrepancies = _fmp_discrepancies(quarters, fmp_enrichment, as_of_date)

    # The classification is not counted here. A reading the harness never derives is a
    # boundary of what this capability does, published once in its limitations, and turning
    # it into a per-request gap says the filings were short of something they never held.
    missing = [*safety_missing, *growth_missing, *identity_missing]
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
        "category_reading": category_reading,
        "valuation": valuation,
        "profitability": profitability,
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
    """Every period the filings speak about, with the latest word on each number.

    Later-filed wins per field, not per period. A quarterly report carries last fiscal year's
    balance sheet as a comparative and no income statement for that year, so replacing the whole
    period left the latest year holding an equity figure and nothing to measure it against --
    while every earlier year, whose quarterly reports had aged out of the eligible window, looked
    complete. Superseding a number the later filing never mentioned is not what a restatement is.
    """

    return _merge_periods(filings, key)[0]


def _merge_periods(filings: list[dict[str, Any]], key: str) -> tuple[list[dict[str, Any]], list[str]]:
    """The merge above, with the period names two different closes reached named separately.

    The label is a projection of a closing date, and a projection can collide. Two facts that
    closed on different dates are two periods however alike their names came out, so merging
    them keeps one figure, discards the other, and says nothing. Both are withheld and the name
    is reported, because a reader has to know a period went missing rather than never existed.
    """

    by_period: dict[str, dict[str, Any]] = {}
    closes: dict[str, set[str]] = {}
    for filing in filings:
        facts = filing.get(key, [])
        if not isinstance(facts, list):
            raise ValueError(f"SEC filing {key} must be a list.")
        for fact in facts:
            if not isinstance(fact, Mapping) or not isinstance(fact.get("period"), str):
                raise ValueError(f"Each {key} fact must identify a period.")
            merged = by_period.setdefault(fact["period"], {"_sources": {}})
            # Provenance is per number. Stamping the whole period with the later filing's date
            # and accounting basis said a US-GAAP revenue had been filed under IFRS, and the
            # margin built from it divided one regime's earnings by another's sales.
            for name in fact:
                if name not in {"period", "end"}:
                    merged["_sources"][name] = {"accounting_basis": filing["accounting_basis"], "filed_at": filing["filed_at"]}
            merged.update({**fact, "accounting_basis": filing["accounting_basis"], "filed_at": filing["filed_at"], "_sources": merged["_sources"]})
            if isinstance(fact.get("end"), str):
                closes.setdefault(fact["period"], set()).add(fact["end"])
    conflicted = sorted(period for period, ends in closes.items() if len(ends) > 1)
    kept = [period for period in by_period if period not in set(conflicted)]
    return [by_period[period] for period in sorted(kept, key=lambda period: _period_sort_key(by_period[period]))], conflicted


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
        if not (_is_number(income) and _is_number(sales) and sales != 0):
            continue
        sources = quarter.get("_sources") or {}
        earnings_from = (sources.get("net_income") or {}).get("accounting_basis", quarter["accounting_basis"])
        sales_from = (sources.get("revenue") or {}).get("accounting_basis", quarter["accounting_basis"])
        # A ratio of two accounting regimes is not a margin. The two halves have to have been
        # measured the same way before their quotient means anything.
        if earnings_from != sales_from:
            continue
        margin.append(_point(quarter, _reported(float(income) / float(sales) * 100), "net_income"))
    return {
        "eps": eps,
        "revenue": revenue,
        "margin_pct": margin,
        "diluted_shares": _metric_series(quarters, "diluted_shares"),
        "eps_yoy_growth": _yoy_growth(eps),
        "revenue_yoy_growth": _yoy_growth(revenue),
        # The latest quarter the company filed, whatever it carried. Every series above drops
        # the quarters whose figure was absent, so reading "the latest" off one of them made
        # the quarter before an empty report into the company's current quarter.
        "latest_filed_period": quarters[-1]["period"] if quarters else None,
    }


def _yoy_growth(series: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each quarter against the same quarter a year earlier, which is the comparison the source makes.

    Quarter on quarter would report a seasonal business as accelerating and decelerating on
    a calendar rather than on its own progress.
    """

    year_ago = {point["period"]: point for point in series}
    growth = []
    for point in series:
        earlier = year_ago.get(_previous_year_quarter(point["period"]))
        # Both quarters have to have been measured the same way. A rise from an IFRS quarter to
        # a US-GAAP one is a change of accounting as much as a change of business, and nothing
        # here can tell the reader which half of it they are looking at.
        if earlier is not None and earlier["accounting_basis"] != point["accounting_basis"]:
            continue
        previous = None if earlier is None else earlier["value"]
        # A percentage change needs a base that means something. From a loss the arithmetic
        # still returns a number and that number has the wrong sign: a loss that doubled
        # comes out as plus one hundred percent, which cleared the growth range and reached
        # `supports_convergence` on evidence that says the opposite.
        if previous is not None and previous > 0:
            growth.append({"period": point["period"], "yoy_pct": _reported((point["value"] / previous - 1) * 100)})
    return growth


def _period_ordinal(period: Any) -> int | None:
    """A period label as a position on the calendar, so adjacency is arithmetic rather than order.

    Every multi-period reading here used to pick values by position after filtering the rows
    that carried the metric, which makes a filter decide adjacency. A company that filed no
    earnings for one year had the two years either side of it compared as consecutive.
    """

    if not isinstance(period, str):
        return None
    if "-Q" in period:
        year, quarter = period.rsplit("-Q", 1)
        try:
            return int(year) * _QUARTERS_PER_YEAR + int(quarter)
        except ValueError:
            return None
    try:
        return int(period)
    except ValueError:
        return None


def _consecutive_tail(points: list[dict[str, Any]], count: int) -> list[dict[str, Any]] | None:
    """The last ``count`` points if their period labels run consecutively, otherwise nothing."""

    if len(points) < count:
        return None
    tail = points[-count:]
    ordinals = [_period_ordinal(point.get("period")) for point in tail]
    if any(ordinal is None for ordinal in ordinals):
        return None
    if any(later - earlier != 1 for earlier, later in zip(ordinals, ordinals[1:])):
        return None
    return tail


def _metric_series(facts: list[dict[str, Any]], metric: str) -> list[dict[str, Any]]:
    return [_point(fact, float(fact[metric]), metric) for fact in facts if _is_number(fact.get(metric))]


def _measured_under(fact: Mapping[str, Any], metric: str) -> str | None:
    """Which accounting regime measured this one number, which is not always the filing's.

    A filer that changes regime carries both in one period, and decision 275 put provenance on
    the number rather than the period for exactly that reason. Every measurement built from two
    numbers has to ask this of both of them before their quotient or their difference means
    anything -- the margin was the only one asking.
    """

    return ((fact.get("_sources") or {}).get(metric) or {}).get("accounting_basis", fact.get("accounting_basis"))


def _point(fact: Mapping[str, Any], value: float, metric: str) -> dict[str, Any]:
    source = (fact.get("_sources") or {}).get(metric) or {"accounting_basis": fact["accounting_basis"], "filed_at": fact["filed_at"]}
    return {
        "period": fact["period"],
        "end": fact.get("end"),
        "value": value,
        "accounting_basis": source["accounting_basis"],
        "filed_at": source["filed_at"],
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

    prior, latest = _prior_year(annual)
    overlapping = _spans_overlap(prior, latest)
    if overlapping:
        prior = None
    return {
        "doctrine_id": _ANNUAL_REQUIREMENT,
        "binds": doctrine.binds(_ANNUAL_REQUIREMENT),
        "computability": doctrine.get_claim(_ANNUAL_REQUIREMENT)["claim"]["computability"],
        "periods": [None if prior is None else prior["period"], None if latest is None else latest["period"]],
        "eps_yoy_pct": _annual_metric_growth(prior, latest, "eps"),
        "revenue_yoy_pct": _annual_metric_growth(prior, latest, "revenue"),
        **({"reason": "annual_periods_overlap"} if overlapping else {"reason": "annual_periods_measured_under_different_accounting_bases"} if _regime_changed(prior, latest, ("eps", "revenue")) else {}),
    }


def _spans_overlap(prior: Mapping[str, Any] | None, latest: Mapping[str, Any] | None) -> bool:
    """Whether two annual periods cover any of the same days.

    A fiscal-year change files a stub or a stretched year, and the year before it then runs
    into it. Their difference is not growth: part of it is the same months counted twice.
    """

    if prior is None or latest is None:
        return False
    ends, starts = prior.get("end"), latest.get("start")
    return isinstance(ends, str) and isinstance(starts, str) and ends >= starts


def _regime_changed(prior: Mapping[str, Any] | None, latest: Mapping[str, Any] | None, metrics: tuple[str, ...]) -> bool:
    if prior is None or latest is None:
        return False
    return any(_measured_under(prior, metric) != _measured_under(latest, metric) for metric in metrics)


def _prior_year(annual: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """The latest annual row, and the row for the year immediately before it if it was filed.

    Found by label rather than by position. Taking the previous row compares a company's 2024
    with its 2022 whenever 2023 is absent, and publishes the result under the two years that
    happened to sit next to each other in the list.
    """

    if not annual:
        return None, None
    latest = annual[-1]
    wanted = _period_ordinal(latest.get("period"))
    if wanted is None:
        return None, latest
    prior = next((fact for fact in annual if _period_ordinal(fact.get("period")) == wanted - 1), None)
    return prior, latest


def _annual_metric_growth(prior: Mapping[str, Any] | None, latest: Mapping[str, Any] | None, metric: str) -> float | None:
    if prior is None or latest is None or not _is_number(prior.get(metric)) or not _is_number(latest.get(metric)):
        return None
    if _measured_under(prior, metric) != _measured_under(latest, metric):
        return None
    previous = float(prior[metric])
    if previous <= 0:
        return None
    return _reported((float(latest[metric]) / previous - 1) * 100)


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


def _growth_read(quarterly: Mapping[str, Any], annual: list[dict[str, Any]], *, market_regime: str | None) -> dict[str, Any]:
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
        "minimum_quarterly_earnings_growth": _banded_window(_MINIMUM_GROWTH, "minimum_yoy_earnings_growth_percent", "minimum_growth_window_quarters", series, quarterly["latest_filed_period"]),
        "superperformance_quarterly_earnings_growth": doctrine.evaluate_band(_SUPERPERFORMANCE, "superperformance_yoy_earnings_growth_percent", latest),
        "bull_market_quarterly_earnings_growth": _bull_market_read(series, latest, market_regime, quarterly["latest_filed_period"]),
        "earnings_deceleration": _deceleration_read(series),
        "two_quarter_rolling_average": _rolling_average(quarterly),
        "margin_trend": _margin_read(quarterly["margin_pct"]),
        "code_33_triple_acceleration": _code_33(quarterly),
        "earnings_without_sales_growth": _earnings_without_sales_growth(quarterly),
        "acceleration_vs_historical_growth_rate": _acceleration_vs_history(quarterly, annual),
        "earnings_history_lookback": _earnings_history_lookback(quarterly),
        "practitioner_readings": _practitioner_readings(series),
    }
    return readings


def _code_33(quarterly: Mapping[str, Any]) -> dict[str, Any]:
    """Three quarters where earnings growth, sales growth and the margin all improved at once.

    The source named the count and declined to name a magnitude, so a quarter accelerates when
    each of the three came in above the quarter before it -- any amount. That is the whole rule,
    and inventing a minimum step would be a second gate the source never stated.

    The run has to reach the latest filed quarter. "A Code 33 situation" is a condition the
    stock is in now, so a run that ended two quarters ago describes a stock that no longer
    qualifies, and reporting the longest run anywhere in the series would say otherwise.
    """

    required = int(doctrine.threshold(_CODE_33, "code_33_quarters_required"))
    judged = _triple_acceleration(quarterly)
    reading = {
        "doctrine_id": _CODE_33,
        "binds": doctrine.binds(_CODE_33),
        "computability": doctrine.get_claim(_CODE_33)["claim"]["computability"],
    }
    # The run has to reach the latest filed quarter, so a latest quarter that cannot be judged
    # at all leaves the reading unavailable. Dropping it and reporting the run behind it
    # published a stale run as the situation the stock is in now.
    if judged and judged[-1][1] is None:
        return {**reading, "state": "unavailable", "reason": "latest_filed_quarter_cannot_be_judged", "latest_filed_quarter": judged[-1][0]}
    if len([entry for entry in judged if entry[1] is not None]) < required:
        return {**reading, "state": "unavailable", "reason": "insufficient_quarters_for_triple_acceleration", "judged_quarters": len([entry for entry in judged if entry[1] is not None])}
    run: list[str] = []
    previous: int | None = None
    for period, accelerated in reversed(judged):
        ordinal = _period_ordinal(period)
        if not accelerated or (previous is not None and previous - ordinal != 1):
            break
        run.insert(0, period)
        previous = ordinal
    return {
        **reading,
        "consecutive_quarters": len(run),
        "quarters": run,
        "latest_judged_quarter": judged[-1][0],
        "gate": doctrine.evaluate_gate(_CODE_33, "code_33_quarters_required", len(run)),
    }


def _triple_acceleration(quarterly: Mapping[str, Any]) -> list[tuple[str, bool | None]]:
    """Per quarter, whether all three cylinders improved on the quarter immediately before it.

    A quarter is judged only when every cylinder has a reading for it and for its predecessor.
    Comparing across a gap in the filings would let a two-year-old margin stand in for last
    quarter's, which is the one comparison that would make a stalled business look accelerating.
    """

    cylinders = (
        {point["period"]: point["yoy_pct"] for point in quarterly["eps_yoy_growth"]},
        {point["period"]: point["yoy_pct"] for point in quarterly["revenue_yoy_growth"]},
        {point["period"]: point["value"] for point in quarterly["margin_pct"]},
    )
    judged: list[tuple[str, bool | None]] = []
    for point in quarterly["eps_yoy_growth"]:
        period, before = point["period"], _previous_quarter(point["period"])
        # A quarter that cannot be judged stays in the list as an unknown rather than being
        # dropped. Removing it made the records either side of it look adjacent, and three
        # surviving records were counted as three consecutive quarters.
        if any(period not in series or before not in series for series in cylinders):
            judged.append((period, None))
            continue
        judged.append((period, all(series[period] > series[before] for series in cylinders)))
    return judged


def _previous_quarter(period: str) -> str:
    if "-Q" not in period:
        return ""
    year, quarter = period.rsplit("-Q", 1)
    try:
        year, quarter = int(year), int(quarter)
    except ValueError:
        return ""
    return f"{year - 1}-Q4" if quarter == 1 else f"{year}-Q{quarter - 1}"


def _earnings_without_sales_growth(quarterly: Mapping[str, Any]) -> dict[str, Any]:
    """Whether the latest quarter's earnings grew while its sales did not.

    The source called cost-cutting-driven improvement short-legged and gave no window for how
    long it can run, so this reports the pattern and stops. It also asks for an operating-margin
    trend, which the filed facts this harness reads do not carry -- named as unread rather than
    substituted with the net margin, which moves with taxes and one-time items too.
    """

    eps, revenue = quarterly["eps_yoy_growth"], quarterly["revenue_yoy_growth"]
    reading = {
        "doctrine_id": _COST_CUTTING,
        "binds": doctrine.binds(_COST_CUTTING),
        "computability": doctrine.get_claim(_COST_CUTTING)["claim"]["computability"],
        "missing_inputs": ["operating_margin_trend"],
    }
    if not eps or not revenue or eps[-1]["period"] != revenue[-1]["period"]:
        return {**reading, "reason": "matching_latest_earnings_and_sales_growth_required", "eps_yoy_pct": None, "revenue_yoy_pct": None, "earnings_grew_without_sales": None}
    return {
        **reading,
        "period": eps[-1]["period"],
        "eps_yoy_pct": eps[-1]["yoy_pct"],
        "revenue_yoy_pct": revenue[-1]["yoy_pct"],
        "earnings_grew_without_sales": eps[-1]["yoy_pct"] > 0 and revenue[-1]["yoy_pct"] <= 0,
    }


def _acceleration_vs_history(quarterly: Mapping[str, Any], annual: list[dict[str, Any]]) -> dict[str, Any]:
    """The company's own three- and five-year compound EPS pace, beside its latest quarter.

    Acceleration in this claim is measured against the company's own history rather than any
    standard, and the figures the source used to illustrate it -- growing twelve percent, then
    forty, then a hundred -- are registered as references. A reference is never compared with a
    ticker's measurement, so no reading here says a rate cleared or missed one of them.

    Three years and five come from the claim's own required inputs, `trailing_3yr_eps_cagr`
    and `trailing_5yr_eps_cagr`, rather than from a threshold: they say which measurement
    exists, not what it has to clear.
    """

    series = [(str(fact.get("period")), float(fact["eps"])) for fact in annual if _is_number(fact.get("eps"))]
    income = [(str(fact.get("period")), float(fact["net_income"])) for fact in annual if _is_number(fact.get("net_income"))]
    three, three_reason, three_start = _compound_growth(series, 3)
    five, _, five_start = _compound_growth(series, 5)
    latest_period = series[-1][0] if series else None
    latest = quarterly["eps_yoy_growth"]
    reading = {
        "doctrine_id": _HISTORICAL_ACCELERATION,
        "binds": doctrine.binds(_HISTORICAL_ACCELERATION),
        "computability": doctrine.get_claim(_HISTORICAL_ACCELERATION)["claim"]["computability"],
        "periods": [series[-4][0], series[-1][0]] if len(series) >= 4 else [fact[0] for fact in series[:1] + series[-1:]],
        "trailing_3yr_eps_cagr_pct": three,
        "trailing_5yr_eps_cagr_pct": five,
        # The two rates the per-share one is made of. A split multiplies the share count and
        # leaves total earnings untouched, so a compound rate that disagrees with the total is
        # reporting a share base that moved rather than a business that did.
        "trailing_3yr_net_income_cagr_pct": _compound_growth(income, 3)[0],
        "trailing_5yr_net_income_cagr_pct": _compound_growth(income, 5)[0],
        "trailing_3yr_diluted_shares_change_pct": _share_change_between(annual, three_start, latest_period),
        "trailing_5yr_diluted_shares_change_pct": _share_change_between(annual, five_start, latest_period),
        "latest_quarterly_eps_yoy_pct": latest[-1]["yoy_pct"] if latest else None,
    }
    return reading if three is not None else {**reading, "reason": three_reason}


def _share_change_between(annual: list[dict[str, Any]], start_period: str | None, end_period: str | None) -> float | None:
    """How far the filed diluted share count moved between two named years.

    Named, not positional. The share context is published as covering the same years the
    per-share rate covers, and reading the tail of the list instead reported a share base that
    moved in years the rate never touched.

    Not adjusted for, only reported. The split itself is a price-history fact and this evaluator
    holds filings, so nothing here can tell a four-for-one split from a share issue four times
    the size -- but both make a per-share rate say something other than what the business did,
    and both show up here.
    """

    if start_period is None or end_period is None:
        return None
    shares = {str(fact.get("period")): float(fact["diluted_shares"]) for fact in annual if _is_number(fact.get("diluted_shares"))}
    if start_period not in shares or end_period not in shares or shares[start_period] <= 0:
        return None
    return _reported((shares[end_period] / shares[start_period] - 1) * 100)


def _compound_growth(series: list[tuple[str, float]], years: int) -> tuple[float | None, str, str | None]:
    """A compound annual rate over ``years`` calendar years, or the reason there isn't one.

    The span is counted in years, not in rows. Reading three rows back lands on 2020 when the
    filings are 2020, 2022, 2024 and 2025, and calls a five-year span a three-year rate.

    Both endpoints must be positive. A negative or zero start describes a recovery from a loss
    as a growth rate, and a negative end sends the fractional power into the complex plane --
    which used to abort the whole capability with a TypeError on any loss-making filer.
    """

    if not series:
        return None, f"insufficient_annual_periods_for_a_{years}_year_rate", None
    by_period = {period: value for period, value in series}
    latest_period, end = series[-1]
    latest = _period_ordinal(latest_period)
    if latest is None:
        return None, f"insufficient_annual_periods_for_a_{years}_year_rate", None
    start_period = str(latest - years)
    if start_period not in by_period:
        return None, f"insufficient_annual_periods_for_a_{years}_year_rate", None
    start = by_period[start_period]
    if start <= 0 or end <= 0:
        return None, "compound_rate_requires_positive_endpoints", start_period
    return _reported(((end / start) ** (1 / years) - 1) * 100), "", start_period


def _one_time_income_exclusion() -> dict[str, Any]:
    """That every EPS figure here is as reported, with nothing stripped out.

    The source's method is exact -- back the nonrecurring gain out and recompute -- and its
    input is prose in a filing footnote, which this harness does not read. Publishing the
    boundary keeps a reader from taking a reported figure for an adjusted one; it is not
    counted as a per-request gap, because no filing was ever short of it.
    """

    return _unread_claim(
        _ONE_TIME_INCOME,
        ["nonrecurring_items_per_share", "filing_footnotes"],
        reason="filing_footnotes_not_read_by_this_harness",
        reported_eps_is_unadjusted=True,
    )


def _category_reading(classification: Mapping[str, Any], quarterly: Mapping[str, Any], annual: list[dict[str, Any]]) -> dict[str, Any]:
    """The claims that read this company's kind, and nothing else's.

    The same earnings history means different things depending on what the company is, and the
    source says so in claims that name one category each. A turnaround is held to a bar a market
    leader is not, so running every category's claim over every ticker would publish six
    readings of which five were about a company this is not.

    Nothing is declared by a filing, so nothing is read until an analyst declares it.
    """

    reader = _CATEGORY_READERS.get(classification["category"])
    return {**classification, "readings": reader(quarterly, annual) if reader else {}}


def _turnaround_reading(quarterly: Mapping[str, Any], annual: list[dict[str, Any]]) -> dict[str, Any]:
    growth = _turnaround_growth(quarterly)
    return {"turnaround_growth_rate_threshold": growth, "turnaround_qualifying_criteria": _turnaround_criteria(quarterly, annual, growth)}


def _turnaround_window() -> list[int]:
    """One to three quarters, which is the two chapters' windows taken together.

    The source gave the scan window twice and not identically -- two or three quarters in one
    chapter, one or two in the other -- and both are registered as references. Widening to the
    union reads every quarter either chapter would have looked at; picking one chapter would
    have silently dropped whichever quarters the other cared about.
    """

    ch6 = doctrine.threshold(_TURNAROUND_GROWTH, "turnaround_growth_window_quarters_ch6")
    ch7 = doctrine.threshold(_TURNAROUND_GROWTH, "turnaround_growth_window_quarters_ch7")
    return [min(*ch6, *ch7), max(*ch6, *ch7)]


def _turnaround_growth(quarterly: Mapping[str, Any]) -> dict[str, Any]:
    """A hundred percent or better, quarter by quarter across the source's window.

    The bar is higher than the one a growth stock is held to, not lower, because a turnaround's
    comparisons are easy: it is coming off quarters bad enough to need turning around.
    """

    window = _turnaround_window()
    series = quarterly["eps_yoy_growth"]
    read = [
        {**doctrine.evaluate_gate(_TURNAROUND_GROWTH, "turnaround_recent_growth_percent", point["yoy_pct"]), "period": point["period"]}
        for point in series[-max(window):]
    ]
    return {
        "doctrine_id": _TURNAROUND_GROWTH,
        "binds": doctrine.binds(_TURNAROUND_GROWTH),
        "computability": doctrine.get_claim(_TURNAROUND_GROWTH)["claim"]["computability"],
        "window_quarters": window,
        "window": read,
        "window_quarters_passing": sum(1 for point in read if point["state"] == "pass"),
    }


def _turnaround_criteria(quarterly: Mapping[str, Any], annual: list[dict[str, Any]], growth: Mapping[str, Any]) -> dict[str, Any]:
    """Two strong quarters, or one big enough to carry the trailing year back to its old peak.

    The claim does not define "strong" and the registry says so, pointing at the hundred-percent
    claim for the quantified version -- so that is what a strong quarter is here, and the reading
    names which claim decided it rather than leaving a reader to guess.

    "Near or above" the old peak is two tests, and only one of them is defined. At or above is
    measured; near is not quantified anywhere in the corpus, so the two figures are published
    beside each other and the word is named as an open judgement instead of being given a
    tolerance this harness invented.
    """

    strong = growth["window_quarters_passing"]
    gate = doctrine.evaluate_gate(_TURNAROUND_CRITERIA, "turnaround_min_strong_quarters", strong)
    trailing, peak, route = _trailing_twelve_months(quarterly["eps"], _metric_series(annual, "eps"))
    at_or_above = None if trailing is None or peak is None else trailing >= peak
    return {
        "doctrine_id": _TURNAROUND_CRITERIA,
        "binds": doctrine.binds(_TURNAROUND_CRITERIA),
        "computability": doctrine.get_claim(_TURNAROUND_CRITERIA)["claim"]["computability"],
        "strong_quarters": strong,
        "strong_means": _TURNAROUND_GROWTH,
        "gate": gate,
        "trailing_12m_eps": _reported(trailing),
        "trailing_12m_route": route,
        "trailing_12m_eps_prior_peak": _reported(peak),
        "trailing_12m_eps_at_or_above_prior_peak": at_or_above,
        "unquantified": ["near_prior_peak_is_unquantified"],
        # Either route satisfies it, so a failed gate settles nothing while the other route
        # went unmeasured. False or unknown is unknown, and publishing it as a refusal reads
        # as evidence the stock fell short of a bar nobody could measure it against.
        "satisfied": True if gate["state"] == "pass" or at_or_above is True else (False if gate["state"] == "fail" and at_or_above is False else None),
    }


def _trailing_twelve_months(series: list[dict[str, Any]], annual: list[dict[str, Any]] | None = None) -> tuple[float | None, float | None, str | None]:
    """Twelve months of filed earnings ending at the latest quarter, and the highest earlier one.

    Four consecutive filed quarters is the direct route and almost never available: no US
    filer publishes a fourth-quarter column, because the 10-K states the year instead. Every
    ticker tried live came back naming four consecutive filed quarters as what it lacked.

    The second route is the same twelve months from three filed numbers -- the last complete
    fiscal year, plus the quarters filed since it closed, minus the quarters those replace.
    Nothing is reconstructed: no quarter nobody filed is published, and the subtraction runs
    on filed figures only. Which route produced the number travels with it, because a reader
    comparing two tickers needs to know when one of them was rolled forward.
    """

    direct = _consecutive_quarter_windows(series)
    rolled = _rolled_forward_windows(series, annual or [])
    # The current trailing year has to end at the latest quarter the company filed. A window
    # that ended four quarters ago is a historical figure, and publishing it as the current
    # denominator put a two-year-old earnings base under today's price.
    latest = series[-1]["period"] if series else None
    current, route = None, None
    if direct and direct[-1][0] == latest:
        current, route = direct[-1][1], _FOUR_FILED_QUARTERS
    elif rolled and rolled[-1][0] == latest:
        current, route = rolled[-1][1], _ROLLED_FORWARD
    # Which route today's year needed says nothing about the years before it. Replacing the
    # whole collection when the current one had to be rolled forward threw away every earlier
    # year built from four filed quarters, and a turnaround then compared itself with a peak
    # it had already beaten. Where both routes reach the same quarter the direct one wins:
    # a sum of four filed quarters is the same twelve months with no subtraction in it.
    by_period = {period: total for period, total in rolled}
    by_period.update({period: total for period, total in direct})
    earlier = [total for period, total in by_period.items() if period != latest]
    return current, max(earlier) if earlier else None, route


def _one_regime(points: list[dict[str, Any]]) -> bool:
    """Whether every number in a sum was measured the same way.

    A twelve-month total is a sum and a difference of filed figures, so a regime change inside
    the window makes the arithmetic add one standard's earnings to another's. The window is
    skipped rather than published with a caveat: there is no reading of it that is right.
    """

    return len({point.get("accounting_basis") for point in points}) <= 1


def _consecutive_quarter_windows(series: list[dict[str, Any]]) -> list[tuple[str, float]]:
    """Every run of four consecutive filed quarters, summed.

    Quarters have to be consecutive for a sum of four to be a year. A window straddling a gap
    in the filings would add up whatever four rows happened to be adjacent in the list and
    call the result twelve months.
    """

    windows = []
    for position in range(len(series) - _QUARTERS_PER_YEAR + 1):
        span = series[position:position + _QUARTERS_PER_YEAR]
        if any(_previous_quarter(later["period"]) != earlier["period"] for earlier, later in zip(span, span[1:])):
            continue
        if not _one_regime(span):
            continue
        windows.append((span[-1]["period"], sum(point["value"] for point in span)))
    return windows


def _quarter_ordinal_on(closing: str) -> int | None:
    """Which quarter a fiscal year's closing date is the end of.

    The quarter ending on that date is the one whose middle falls half a quarter behind it,
    which is how the provider named every quarter it published -- so the same date reaches the
    same label from both directions.
    """

    try:
        middle = date.fromisoformat(closing) - timedelta(days=_HALF_QUARTER_DAYS)
    except (TypeError, ValueError):
        return None
    return _period_ordinal(f"{middle.year}-Q{(middle.month - 1) // 3 + 1}")


def _rolled_forward_windows(series: list[dict[str, Any]], annual: list[dict[str, Any]]) -> list[tuple[str, float]]:
    """A trailing year at each quarter: the last closed fiscal year, rolled forward and back.

    The fiscal year is found by its closing date rather than by its label, because a January
    or September close makes the label say a year the quarters do not. The quarters since that
    close have to be consecutive and to end at the quarter being measured -- otherwise the
    window has a hole in it, and a hole makes the subtraction silently drop a quarter of
    earnings from one side and not the other.
    """

    years = sorted((point for point in annual if isinstance(point.get("end"), str)), key=lambda point: point["end"])
    by_ordinal = {_period_ordinal(point["period"]): point for point in series if _period_ordinal(point["period"]) is not None}
    windows = []
    for point in series:
        end, ordinal = point.get("end"), _period_ordinal(point["period"])
        if not isinstance(end, str) or ordinal is None:
            continue
        closed = next((year for year in reversed(years) if year["end"] < end), None)
        if closed is None:
            continue
        since = sorted(
            (other for other in series if isinstance(other.get("end"), str) and closed["end"] < other["end"] <= end and _period_ordinal(other["period"]) is not None),
            key=lambda other: other["end"],
        )
        ordinals = [_period_ordinal(other["period"]) for other in since]
        # Every quarter between the close and here, not merely a consecutive run of them. Filed
        # Q2 with Q1 absent is consecutive with itself and ends in the right place, and the
        # subtraction then quietly assumed the missing quarter was unchanged year over year --
        # a fifth of a year's earnings dropped with nothing in the envelope saying so.
        last = _quarter_ordinal_on(closed["end"])
        if last is None or not 0 < ordinal - last < _QUARTERS_PER_YEAR:
            continue
        if ordinals != list(range(last + 1, ordinal + 1)):
            continue
        replaced = [by_ordinal.get(position - _QUARTERS_PER_YEAR) for position in ordinals]
        if any(quarter is None for quarter in replaced):
            continue
        if not _one_regime([closed, *since, *replaced]):
            continue
        total = closed["value"] + sum(other["value"] for other in since) - sum(quarter["value"] for quarter in replaced)
        windows.append((point["period"], total))
    return windows


def _market_leader_reading(quarterly: Mapping[str, Any], annual: list[dict[str, Any]]) -> dict[str, Any]:
    """A market leader's annual pace, against the two figures the source gave for one.

    Twenty percent is a marker -- "they generally grow earnings at a rate of 20 percent or
    higher" names a value and declines to bound it -- so the reading is the measurement and its
    distance, never a pass. Thirty-five to forty-five is a band, and the source attached it to a
    best stretch of five or ten years, so it is measured over the best such stretch on file and
    reports unavailable when the filings do not reach back that far.
    """

    series = [(str(fact.get("period")), float(fact["eps"])) for fact in annual if _is_number(fact.get("eps"))]
    span, best, stretch_start, stretch_end = _best_stretch(series)
    reading = {
        "doctrine_id": _MARKET_LEADER,
        "binds": doctrine.binds(_MARKET_LEADER),
        "computability": doctrine.get_claim(_MARKET_LEADER)["claim"]["computability"],
        "latest_annual_growth": doctrine.evaluate_marker(_MARKET_LEADER, "market_leader_min_earnings_growth_percent", _annual_metric_growth(*_prior_year(annual), "eps")),
        "best_stretch": doctrine.evaluate_band(_MARKET_LEADER, "market_leader_best_stretch_growth_percent", best),
        "best_stretch_years": doctrine.threshold(_MARKET_LEADER, "market_leader_best_stretch_years"),
        "missing_inputs": ["market_share_trend", "industry_classification"],
    }
    if span is None:
        return reading
    # The winning stretch is the highest per-share rate on file, and a share base that shrank
    # raises that rate without the business having done anything. What the count did over the
    # same years travels with it so the reader can see which happened.
    return {
        **reading,
        "best_stretch_span_years": span,
        "best_stretch_periods": [stretch_start, stretch_end],
        "best_stretch_diluted_shares_change_pct": _share_change_between(annual, stretch_start, stretch_end),
    }


def _best_stretch(series: list[tuple[str, float]]) -> tuple[int | None, float | None, str | None, str | None]:
    """The highest compound annual rate over any stretch the source's span covers.

    Consecutive years only. A stretch spanning a year the company did not file would compound
    across a gap and report the average of two eras as one company's best run.
    """

    lower, upper = doctrine.threshold(_MARKET_LEADER, "market_leader_best_stretch_years")
    best: tuple[int | None, float | None, str | None, str | None] = (None, None, None, None)
    for span in range(int(lower), int(upper) + 1):
        for position in range(len(series) - span):
            window = series[position:position + span + 1]
            ordinals = [_period_ordinal(period) for period, _ in window]
            if any(ordinal is None for ordinal in ordinals) or any(later - earlier != 1 for earlier, later in zip(ordinals, ordinals[1:])):
                continue
            rate, _, _ = _compound_growth(window, span)
            if rate is not None and (best[1] is None or rate > best[1]):
                best = (span, rate, window[0][0], window[-1][0])
    return best


def _institutional_favorite_reading(quarterly: Mapping[str, Any], annual: list[dict[str, Any]]) -> dict[str, Any]:
    """A mature company's pace, published without a range to compare it against.

    The source described the growth as "low to middle teens", which the registry records as a
    descriptor rather than a numeric range, and the claim carries no threshold. So the annual
    rate is published and nothing is said about whether it cleared anything.
    """

    return {
        "doctrine_id": _INSTITUTIONAL_FAVORITE,
        "binds": doctrine.binds(_INSTITUTIONAL_FAVORITE),
        "computability": doctrine.get_claim(_INSTITUTIONAL_FAVORITE)["claim"]["computability"],
        "latest_annual_eps_growth_pct": _annual_metric_growth(*_prior_year(annual), "eps"),
        "missing_inputs": ["dividend_growth_history"],
        "unquantified": ["low_to_middle_teens_is_a_descriptor_not_a_range"],
    }


def _cyclical_reading(quarterly: Mapping[str, Any], annual: list[dict[str, Any]]) -> dict[str, Any]:
    """Of the four signals the source lists for a cyclical's position, the one that is filed.

    Earnings direction is in the filings. The price-earnings series, the dividend history and
    the industry classification are not, and the source's reading is inverse -- a high multiple
    when the stock is poised to rally, a low one near the end -- so naming a cycle position from
    the earnings direction alone would invert the very reading the claim exists to warn about.
    """

    series = quarterly["eps_yoy_growth"]
    latest = series[-1]["yoy_pct"] if series else None
    direction = "unavailable" if latest is None else "rising" if latest > 0 else "falling" if latest < 0 else "flat"
    return {
        "doctrine_id": _CYCLICAL,
        "binds": doctrine.binds(_CYCLICAL),
        "computability": doctrine.get_claim(_CYCLICAL)["claim"]["computability"],
        "earnings_direction": direction,
        "latest_quarterly_eps_yoy_pct": latest,
        "missing_inputs": ["pe_ratio_series", "dividend_history", "industry_classification"],
    }


def _top_competitor_boundary(quarterly: Mapping[str, Any], annual: list[dict[str, Any]]) -> dict[str, Any]:
    """Which two or three names lead a group is a ranking, and this evaluator holds one company."""

    return {
        "top_competitor_reading": _unread_claim(
            _TOP_COMPETITOR,
            ["peer_group_eps_growth", "peer_group_revenue_growth", "peer_group_margins", "peer_group_relative_strength"],
            reason="peer_group_not_held_by_this_capability",
            competitors_to_track=doctrine.threshold(_TOP_COMPETITOR, "top_competitors_to_track_count"),
        )
    }


def _laggard_boundary(quarterly: Mapping[str, Any], annual: list[dict[str, Any]]) -> dict[str, Any]:
    """A laggard is defined by the group it lags, which is evidence from outside this evaluator."""

    return {
        "laggard_fundamentals_reading": _unread_claim(
            _LAGGARD,
            ["peer_group_eps_growth", "peer_group_revenue_growth", "relative_price_performance"],
            reason="peer_group_not_held_by_this_capability",
        )
    }


def _unread_claim(claim_id: str, missing_inputs: list[str], **extra: Any) -> dict[str, Any]:
    """A claim named with what it needed and did not get, rather than left out of the output.

    An omitted reading and an unrunnable one look the same to a reader, and only one of them is
    a boundary of what this capability does. These are not counted as per-request gaps: no
    filing was ever short of them.
    """

    return {
        "doctrine_id": claim_id,
        "binds": doctrine.binds(claim_id),
        "computability": doctrine.get_claim(claim_id)["claim"]["computability"],
        "state": "not_evaluated",
        "missing_inputs": missing_inputs,
        **extra,
    }


_CATEGORY_READERS = {
    "turnaround": _turnaround_reading,
    "market_leader": lambda quarterly, annual: {"market_leader_earnings_growth_pace": _market_leader_reading(quarterly, annual)},
    "institutional_favorite": lambda quarterly, annual: {"institutional_favorite_growth_pace": _institutional_favorite_reading(quarterly, annual)},
    "cyclical": lambda quarterly, annual: {"cyclical_inverse_pe_and_signals": _cyclical_reading(quarterly, annual)},
    "top_competitor": _top_competitor_boundary,
    "past_leader_or_laggard": _laggard_boundary,
}


def _valuation(
    filings: list[dict[str, Any]],
    quarterly: Mapping[str, Any],
    annual: list[dict[str, Any]],
    as_of: date,
    *,
    last_close: float | None,
    breakout_close: float | None,
    breakout_date: str | None,
) -> dict[str, Any]:
    """What the price says about the earnings, and what the source says about that.

    The price is not in the filings, so it arrives declared. Everything here is framed by the
    claim that a multiple on its own ranks among the most useless statistics on Wall Street:
    the number is published, and no state anywhere derives a verdict from it.
    """

    trailing, _, route = _trailing_twelve_months(quarterly["eps"], _metric_series(annual, "eps"))
    return {
        "price_earnings_ratio": _price_earnings(last_close, trailing, route, _trailing_share_base(quarterly, annual)),
        "anti_low_pe_bargain_trap": _unread_claim(
            _ANTI_LOW_PE,
            ["peer_group_pe_ratios", "eps_growth_comparison"],
            reason="peer_group_not_held_by_this_capability",
        ),
        "pe_expansion": _pe_expansion(filings, as_of, last_close=last_close, trailing=trailing, breakout_close=breakout_close, breakout_date=breakout_date),
        "practitioner_views": [_practitioner_view(claim_id) for claim_id in _PE_VIEWS],
    }


def _trailing_share_base(quarterly: Mapping[str, Any], annual: list[dict[str, Any]]) -> dict[str, Any]:
    """The filed diluted share counts the trailing year was built out of.

    A rolled-forward year adds a fiscal year's per-share figure to quarters filed after it, and
    a split between the two restates one side and not the other -- so the sum is off by the
    split ratio and nothing in the arithmetic can see it. The split is a price-history fact and
    this evaluator holds filings, so it is reported rather than adjusted for, in the same shape
    decision 273 chose for the compound rates: the two counts, side by side, for the reader.
    """

    latest_quarter = next((point["value"] for point in reversed(quarterly.get("diluted_shares") or [])), None)
    latest_year = next((float(fact["diluted_shares"]) for fact in reversed(annual) if _is_number(fact.get("diluted_shares"))), None)
    return {"latest_annual": latest_year, "latest_quarter": latest_quarter}


def _price_earnings(last_close: float | None, trailing: float | None, route: str | None = None, share_base: dict[str, Any] | None = None) -> dict[str, Any]:
    """The close over the trailing twelve months of filed earnings.

    A company that lost money has no meaningful multiple, and the arithmetic would still return
    one -- a negative number that sorts below every cheap stock in a screen. So it is refused
    by name rather than published.
    """

    reading = {
        # Two claims read the same number, so both are named: what it is worth alone, and what
        # a low one is worth. A block that cited only one would hide the other from the reader.
        "doctrine_ids": [_PE_USELESS, _ANTI_LOW_PE],
        "last_close": _reported(last_close) if _is_number(last_close) else None,
        # Published rounded, divided raw. Rounding the sum first turned a company earning a
        # ten-thousandth of a cent into a company that earned nothing.
        "trailing_12m_eps": _reported(trailing),
        "trailing_12m_route": route,
        "trailing_12m_diluted_shares": share_base,
    }
    if not _is_number(last_close):
        return {**reading, "state": "unavailable", "missing_inputs": ["last_close"], "pe_ratio": None}
    if trailing is None:
        return {**reading, "state": "unavailable", "missing_inputs": ["filed_quarters_for_a_complete_trailing_year"], "pe_ratio": None}
    # A sum that ran past what binary64 can hold is an arithmetic failure, not an absence. It
    # used to leave through the same door as "the quarters were never filed", which tells a
    # reader to go looking for a filing that is already there.
    if not math.isfinite(trailing):
        return {**reading, "state": "not_meaningful", "reason": "trailing_12m_eps_beyond_arithmetic_range", "pe_ratio": None}
    if trailing <= 0:
        return {**reading, "state": "not_meaningful", "reason": "trailing_12m_eps_not_positive", "pe_ratio": None}
    return {**reading, "state": "reported", "pe_ratio": _reported(float(last_close) / trailing)}


def _pe_expansion(
    filings: list[dict[str, Any]],
    as_of: date,
    *,
    last_close: float | None,
    trailing: float | None,
    breakout_close: float | None,
    breakout_date: str | None,
) -> dict[str, Any]:
    """How far the multiple travelled between the breakout and now, over how long.

    The source gave the same finding twice, once as a percentage and once as a multiple -- "the
    P/E expands by 100 to 200 percent... (or two to three times)" -- and both are registered as
    bands, so both are reported where the measurement sat rather than as a signal that fired.

    The multiple at the breakout is computed from what had been filed by then. Using today's
    filings would credit the buyer with a quarter published six weeks after they bought, and
    would shrink every expansion this claim exists to notice.
    """

    reading = {"doctrine_id": _PE_EXPANSION, "binds": doctrine.binds(_PE_EXPANSION), "computability": doctrine.get_claim(_PE_EXPANSION)["claim"]["computability"]}
    # Name what was actually absent. Both names went out whenever either was missing, so a
    # caller who supplied a date and whose price provider came up short was told the date was
    # missing too -- while the envelope echoed it back in the request beside the reading.
    absent = [name for name, value in (("breakout_close", breakout_close if _is_number(breakout_close) else None), ("breakout_date", breakout_date)) if value is None]
    if absent:
        return {**reading, "state": "unavailable", "missing_inputs": absent, **({"breakout_date": breakout_date} if breakout_date is not None else {})}
    breakout = _parse_date(breakout_date, "breakout_date")
    if breakout > as_of:
        raise ValueError("breakout_date must not be after as_of.")
    known = _eligible_filings(filings, breakout)
    at_breakout, _, at_breakout_route = _trailing_twelve_months(_metric_series(_latest_periods(known, "quarterly"), "eps"), _metric_series(_latest_periods(known, "annual"), "eps"))
    current = _price_earnings(last_close, trailing)
    # Both ratios are divided raw and rounded only on the way out. Dividing the two published
    # numbers instead put a measurement a hair under the source's two-times edge exactly on it,
    # and the band then read as inside a range the stock had not reached.
    now = None if trailing is None or trailing <= 0 or not _is_number(last_close) else float(last_close) / trailing
    then = None if at_breakout is None or not math.isfinite(at_breakout) or at_breakout <= 0 else float(breakout_close) / at_breakout
    months = _completed_months(breakout, as_of)
    expanded = None if then is None or not then > 0 or now is None else now / then
    return {
        **reading,
        "breakout_date": breakout.isoformat(),
        "trailing_12m_eps_at_breakout": _reported(at_breakout),
        "trailing_12m_route_at_breakout": at_breakout_route,
        "filings_available_at_breakout": [filing["filed_at"] for filing in known],
        "pe_ratio_at_breakout": _reported(then),
        "pe_ratio_current": current["pe_ratio"],
        "expansion": doctrine.evaluate_band(_PE_EXPANSION, "pe_expansion_late_stage_signal_percent", None if expanded is None else _reported((expanded - 1) * 100)),
        "multiple": doctrine.evaluate_band(_PE_EXPANSION, "pe_expansion_historical_average_multiple", None if expanded is None else _reported(expanded)),
        "elapsed": doctrine.evaluate_band(_PE_EXPANSION, "pe_expansion_signal_window_months", months),
    }


def _completed_months(start: date, end: date) -> int:
    """Months that have finished between two dates, not the calendar months they span.

    A window the source gave in months counts elapsed ones, and a month that has not reached
    its own day has not elapsed: the difference put a stock inside the twelve-to-twenty-four
    window as much as thirty days before it arrived there.
    """

    months = (end.year - start.year) * _MONTHS_PER_YEAR + (end.month - start.month)
    # A month that began on the 31st is over on the 28th of February, because February has no
    # 31st for it to wait for. Counting the day alone dropped a month at every fiscal quarter
    # that closes on a month end, which is most of them.
    if end.day < start.day and (end + timedelta(days=1)).month == end.month:
        return months - 1
    return months


def _return_on_equity(annual: list[dict[str, Any]]) -> dict[str, Any]:
    """What a year's earnings returned on the equity that produced them.

    The source's use of it is comparative -- "use it to compare your stock with other stocks in
    the same industry group" -- and this evaluator holds one company, so half the claim is a
    named gap. The band is still measured, because fifteen to seventeen percent is a range the
    source gave as a range.

    Two of the practitioners in this corpus say they never look at it. The registry records that
    disagreement, and it travels with the reading rather than being resolved here.
    """

    claim = doctrine.get_claim(_RETURN_ON_EQUITY)["claim"]
    reading = {
        "doctrine_id": _RETURN_ON_EQUITY,
        "binds": doctrine.binds(_RETURN_ON_EQUITY),
        "computability": claim["computability"],
        "missing_inputs": ["industry_group_roe_comparison"],
        "disagrees_with": claim.get("disagrees_with", []),
    }
    latest = next(
        (fact for fact in reversed(annual) if _is_number(fact.get("net_income")) and _is_number(fact.get("stockholders_equity"))),
        None,
    )
    if latest is None:
        return {**reading, "state": "unavailable", "reason": "annual_net_income_and_stockholders_equity_required", "roe_pct": None, "band": doctrine.evaluate_band(_RETURN_ON_EQUITY, "roe_min", None)}
    if _measured_under(latest, "net_income") != _measured_under(latest, "stockholders_equity"):
        return {**reading, "state": "unavailable", "reason": "net_income_and_equity_measured_under_different_accounting_bases", "period": latest.get("period"), "roe_pct": None, "band": doctrine.evaluate_band(_RETURN_ON_EQUITY, "roe_min", None)}
    equity = float(latest["stockholders_equity"])
    if equity <= 0:
        # A negative book value returns a ratio whose sign says the opposite of what it means:
        # a loss on negative equity comes out positive. It is refused rather than published.
        return {**reading, "state": "not_meaningful", "reason": "stockholders_equity_not_positive", "period": latest.get("period"), "roe_pct": None, "band": doctrine.evaluate_band(_RETURN_ON_EQUITY, "roe_min", None)}
    roe = _reported(float(latest["net_income"]) / equity * 100)
    return {
        **reading,
        "state": "reported",
        "period": latest.get("period"),
        "net_income": _reported(float(latest["net_income"])),
        "stockholders_equity": _reported(equity),
        "roe_pct": roe,
        "band": doctrine.evaluate_band(_RETURN_ON_EQUITY, "roe_min", roe),
    }


def _annual_only(filings: list[dict[str, Any]], growth_missing: list[str]) -> list[str]:
    """One gap instead of three when the registrant does not file quarters at all.

    A foreign private issuer files an annual 20-F and nothing in between. Listing the three
    quarterly series as missing reads like data that was not fetched and might turn up, and the
    doctrine's growth claims are quarterly, so waiting will not fill it. Naming the reason is
    the difference between an incomplete reading and one a reader keeps re-running.
    """

    quarterly_gaps = [gap for gap in growth_missing if gap.startswith("quarterly_")]
    if not quarterly_gaps or not filings:
        return growth_missing
    if not all(isinstance(filing.get("form"), str) and filing["form"].split("/", 1)[0] in _ANNUAL_ONLY_FORMS for filing in filings):
        return growth_missing
    return [gap for gap in growth_missing if gap not in quarterly_gaps] + ["quarterly_facts_not_filed_by_this_registrant"]


def _practitioner_readings(series: list[dict[str, Any]]) -> dict[str, Any]:
    """The same quarterly growth, read the three other ways this corpus records.

    None of these can move a verdict. The canonical layer is the default and the practice layer
    fills execution gaps rather than overriding, so what these add is the disagreement itself --
    which a reader weighing a borderline measurement needs and cannot get from one voice.
    """

    latest = series[-1]["yoy_pct"] if series else None
    return {
        "zanger_quarterly_growth_target": {
            **_practitioner_view(_ZANGER_GROWTH),
            "band": doctrine.evaluate_band(_ZANGER_GROWTH, "yoy_quarterly_earnings_growth_target", latest),
        },
        "minervini_sequential_acceleration": {
            **_practitioner_view(_SEQUENTIAL_ACCELERATION),
            "lookback_quarters": doctrine.threshold(_SEQUENTIAL_ACCELERATION, "earnings_acceleration_lookback"),
            **_sequential_reading(series),
        },
        "ritchie_explosive_growth_only": _practitioner_view(_RITCHIE_GROWTH),
    }


def _sequential_acceleration(series: list[dict[str, Any]]) -> int | None:
    """How many quarters in a row, ending at the latest, came in faster than the one before.

    Capped at the quarters the source inspects, and the registry says why that cap is not a
    range: a fifth accelerating quarter is not adverse, it is simply past where he looked.
    """

    limit = int(max(doctrine.threshold(_SEQUENTIAL_ACCELERATION, "earnings_acceleration_lookback")))
    # A run of zero says the latest quarter did not come in faster than the one before it. With
    # no quarter before it on file nobody has said that, and the two readings are not the same
    # evidence: one is a stock that decelerated, the other is a history too short to tell.
    ordinals = [_period_ordinal(point["period"]) for point in series[-2:]]
    if len(ordinals) < 2 or None in ordinals or ordinals[1] - ordinals[0] != 1:
        return None
    run = 0
    for earlier, later in zip(reversed(series[:-1]), reversed(series[1:])):
        ordinals = (_period_ordinal(earlier["period"]), _period_ordinal(later["period"]))
        # "Sequentially" is the source's own word. A quarter the company did not file is not
        # the quarter before the one after it, however adjacent the two records look.
        if None in ordinals or ordinals[1] - ordinals[0] != 1:
            break
        if later["yoy_pct"] <= earlier["yoy_pct"] or run >= limit:
            break
        run += 1
    return run


def _sequential_reading(series: list[dict[str, Any]]) -> dict[str, Any]:
    """The run, or the fact that no quarter on file has the quarter before it beside it."""

    run = _sequential_acceleration(series)
    if run is None:
        return {"state": "unavailable", "reason": "no_adjacent_quarter_to_compare", "consecutive_accelerating_quarters": None}
    return {"state": "reported", "consecutive_accelerating_quarters": run}


def _practitioner_view(claim_id: str) -> dict[str, Any]:
    """One practitioner's position, quoted rather than summarised.

    A judgment-only claim's whole content is the sentence somebody said. Paraphrasing it would
    put this harness's words under their name, and these are exactly the claims where the
    difference between "never looks at it" and "rarely concerns himself with it" is the point.
    """

    record = doctrine.get_claim(claim_id)
    return {
        "doctrine_id": claim_id,
        "attributed_to": record["claim"]["attributed_to"],
        "binds": doctrine.binds(claim_id),
        "computability": record["claim"]["computability"],
        "quotation": record["provenance"]["quotations"][0]["text"],
    }


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


def _bull_market_read(series: list[dict[str, Any]], latest: float | None, market_regime: str | None, latest_filed: str | None) -> dict[str, Any]:
    """The bull-market pace, which the claim asks for a regime classification to read at all."""

    if market_regime is None:
        return {"doctrine_id": _BULL_MARKET, "state": "unavailable", "missing_inputs": ["market_regime_classification"]}
    if market_regime not in MARKET_REGIMES:
        raise ValueError(f"market_regime must be one of {', '.join(MARKET_REGIMES)}.")
    if market_regime != "bull":
        return {"doctrine_id": _BULL_MARKET, "state": "not_applicable", "market_regime": market_regime}
    return {**_banded_window(_BULL_MARKET, "bull_market_yoy_earnings_growth_percent", "bull_market_growth_window_quarters", series, latest_filed), "market_regime": market_regime}


def _banded_window(claim_id: str, band: str, window: str, series: list[dict[str, Any]], latest_filed: str | None) -> dict[str, Any]:
    """A band read on the latest quarter, with the quarters the source's own window covers beside it.

    Both of these sentences name a window as well as a range -- "in the most recent one, two,
    or three quarters", "in the most recent two to three quarters" -- and reading only the
    latest quarter published a stock whose two prior quarters ran well above the range as
    though they had never been filed.

    The window is registered as a reference, so nothing is compared against it: it decides how
    many quarters get reported and nothing else. The headline stays the latest quarter, because
    that is the one quarter every length of the source's window contains, and because a single
    owner for the reading keeps the count beside it from reading as a second verdict.
    """

    quarters = int(max(doctrine.threshold(claim_id, window)))
    # The headline is the latest quarter the company filed or it is nothing. A quarter filed
    # without the figure leaves no year-over-year pair, and reading the pair before it
    # published a stale quarter's growth as the company's current growth.
    reachable = bool(series) and series[-1]["period"] == latest_filed
    reading = doctrine.evaluate_band(claim_id, band, series[-1]["yoy_pct"] if reachable else None)
    if not reachable:
        reading = {**reading, "reason": "latest_filed_quarter_has_no_year_over_year_pair", "latest_filed_period": latest_filed}
    # "The most recent three quarters" means three quarters in a row. A window that reaches back
    # over a quarter nobody filed reports the one before the gap as though it were recent.
    held: list[dict[str, Any]] = []
    for length in range(quarters, 0, -1):
        tail = _consecutive_tail(series, length)
        if tail is not None:
            held = tail
            break
    read = [{**doctrine.evaluate_band(claim_id, band, point["yoy_pct"]), "period": point["period"], "yoy_pct": point["yoy_pct"]} for point in held]
    return {
        **reading,
        "window_quarters": doctrine.threshold(claim_id, window),
        "window": read,
        "window_quarters_within_or_above": sum(1 for point in read if point["state"] in {"within_source_range", "above_source_range"}),
    }


def _earnings_history_lookback(quarterly: Mapping[str, Any]) -> dict[str, Any]:
    """Whether the one-to-two years the source looks back over hold any acceleration at all.

    "Some form of earnings and sales acceleration" is as far as the source quantified it, so
    this names the quarters where both the earnings growth rate and the sales growth rate came
    in above the quarter before, and stops. It is looser than Code 33 on purpose -- that one
    counts a run and wants margins too -- and the two disagreeing is information, not a bug.

    The lookback bounds year-over-year rates, not filings, and a rate needs the same quarter a
    year earlier beside it. So two years of lookback reads across three years of filings, and
    what is published is the periods actually examined rather than a count a reader would have
    to reconcile against the filings list.
    """

    years = doctrine.threshold(_HISTORY_LOOKBACK, "earnings_trend_lookback_years")
    eps = {point["period"]: point["yoy_pct"] for point in quarterly["eps_yoy_growth"]}
    revenue = {point["period"]: point["yoy_pct"] for point in quarterly["revenue_yoy_growth"]}
    read = quarterly["eps_yoy_growth"][-(int(max(years)) * _QUARTERS_PER_YEAR):]
    accelerating = []
    comparable = 0
    for point in read:
        period, before = point["period"], _previous_quarter(point["period"])
        if any(period not in series or before not in series for series in (eps, revenue)):
            continue
        comparable += 1
        if eps[period] > eps[before] and revenue[period] > revenue[before]:
            accelerating.append(period)
    return {
        "doctrine_id": _HISTORY_LOOKBACK,
        "binds": doctrine.binds(_HISTORY_LOOKBACK),
        "computability": doctrine.get_claim(_HISTORY_LOOKBACK)["claim"]["computability"],
        "lookback_years": years,
        "periods_examined": [point["period"] for point in read],
        "quarters_accelerating_in_both": accelerating,
        # Comparable means both metrics have this quarter and the quarter before it. With none
        # of the examined quarters comparable, "no acceleration" is not what the filings say --
        # they say nothing, and a reader cannot tell those two apart from a bare false.
        **({"state": "reported", "some_form_of_acceleration": bool(accelerating)} if comparable
           else {"state": "unavailable", "reason": "no_quarter_with_the_quarter_before_it_on_file", "some_form_of_acceleration": None}),
    }


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
        # Consecutive quarters or nothing. Averaging whatever two records happen to sit at the
        # end of the list smooths across a quarter the company never filed and calls the result
        # a two-quarter average.
        tail = _consecutive_tail(quarterly[f"{name}_yoy_growth"], window)
        averages[f"{name}_yoy_pct"] = _reported(sum(point["yoy_pct"] for point in tail) / window) if tail else None
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

    if _consecutive_tail(annual, 2) is None:
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
    if any(value is None for value in ratios.values()):
        # Both balances were filed, so nothing is missing -- but a line that started at zero
        # has no growth rate, and the reading cannot call itself reported with its own ratios
        # empty beside it.
        return {**reading, **ratios, "state": "not_meaningful", "reason": "a_balance_that_started_at_zero_has_no_growth_rate"}
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
    """Rounded for the reader, never for the comparison -- and never a value JSON cannot carry."""

    return None if value is None or not _is_number(value) else round(value, _REPORTED_PRECISION)


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
    """Whether the filed growth supports convergence, read from every reading that bears on it.

    A band contributes to convergence and never carries it alone -- the governing contract says
    so, and this used to break it in the one place it mattered: the latest quarter landing
    inside 20-25 percent produced `supports_convergence` by itself, and a company whose annual
    earnings and sales had both halved cleared it that way.

    Convergence is the source's own word for a conjunction, so what decides is the conjunction:
    the quarterly band at or above its range, and the annual claim's own direction. Any of them
    prompting review makes the state `review`, which is no-trade rather than rejection -- every
    fundamentals claim in the registry carries `needs_review`, so nothing here can reject, and
    marginal evidence never earns a pass. The higher bars are read from the same quarterly
    number and reported as context, since a candidate can support convergence without being a
    superperformer.
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
    review = []
    if minimum["state"] not in {"within_source_range", "above_source_range"}:
        review.append("quarterly_earnings_growth_below_source_range")
    # Direction, not magnitude. The annual claim is a constitution-level one -- quarterly
    # strength has to translate into annual results -- and it names no number, so what is read
    # is the sign the claim itself points at. A year whose earnings halved is not a year that
    # translated, whatever the latest quarter did.
    if not annual["eps_yoy_pct"] > 0:
        review.append("annual_earnings_did_not_grow")
    if not annual["revenue_yoy_pct"] > 0:
        review.append("annual_sales_did_not_grow")
    return {
        "state": "supports" if not review else "review",
        "read": [_MINIMUM_GROWTH, _ANNUAL_REQUIREMENT],
        "review_reasons": review,
        "minimum_growth_state": minimum["state"],
        "measured_yoy_pct": minimum["measured"],
        "annual_eps_yoy_pct": annual["eps_yoy_pct"],
        "annual_revenue_yoy_pct": annual["revenue_yoy_pct"],
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
    """A value the arithmetic here can use, which excludes the two floats that are not numbers.

    `nan` and the infinities pass every isinstance check, survive every comparison as False,
    and then break strict JSON encoding at the envelope -- after a reading has already been
    published beside them saying it was measured.
    """

    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
