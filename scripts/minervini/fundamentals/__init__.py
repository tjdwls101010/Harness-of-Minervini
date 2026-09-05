"""Point-in-time filed-fundamentals evaluator.

The public evaluator deliberately accepts only normalized SEC filed facts and
optional FMP enrichment. Narrative is not a numeric evidence input.
"""

from __future__ import annotations

# Keep orchestration lookups here so existing module-level overrides still apply.

from datetime import date, timedelta
import math
from typing import Any, Mapping
from ..dates import parse_iso
from ..numbers import REPORTED_PRECISION as _REPORTED_PRECISION
from .. import doctrine


_REPEATED_CHARGE = "fundamentals.repeated_one_time_charge_red_flag"
_TAX_DISCLOSURE = "fundamentals.tax_disclosure_red_flag"
# One agrees without a number and two say they never look at it. The Minervini claim records
# the disagreement as prose; naming the claims puts the sentences themselves in front of the
# reader, which is the only form in which "never" and "secondary" stay distinguishable.
_ROE_VIEWS = (
    "practitioners.fundamentals.ryan_roe_margins_important_no_number",
    "practitioners.fundamentals.zanger_never_roe_sometimes_margins",
    "practitioners.fundamentals.ritchie_never_roe_margins_secondary",
)


SEC_SOURCE = "sec_filed_facts"


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

    quarterly = _quarterly_read(quarters, quarterly_conflicts)
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
        # Every declaration the payload acts on, including the regime: the bull-market band is
        # read only when one was declared, so leaving it out of this list had the envelope
        # disagreeing with the reading beside it about what the caller supplied.
        "declared_inputs": {"going_concern": going_concern, "accounting_integrity": accounting_integrity, "leader_category": leader_category, "market_regime": market_regime},
        "fundamentals_state": fundamentals_state,
        "missing": _dedupe(missing),
    }


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


from .categories import _CATEGORY_READERS, _CYCLICAL, _INSTITUTIONAL_FAVORITE, _LAGGARD, _MARKET_LEADER, _TOP_COMPETITOR, _TURNAROUND_CRITERIA, _TURNAROUND_GROWTH, _best_stretch, _category_reading, _cyclical_reading, _institutional_favorite_reading, _laggard_boundary, _market_leader_reading, _top_competitor_boundary, _turnaround_criteria, _turnaround_growth, _turnaround_reading, _turnaround_window
from .growth import MARKET_REGIMES, _BULL_MARKET, _CODE_33, _DECELERATION, _HISTORICAL_ACCELERATION, _HISTORY_LOOKBACK, _RITCHIE_GROWTH, _SEQUENTIAL_ACCELERATION, _SMOOTHING, _STALE_HEADLINE, _SUPERPERFORMANCE, _ZANGER_GROWTH, _acceleration_vs_history, _annual_growth, _annual_metric_growth, _banded_window, _bull_market_read, _code_33, _deceleration_read, _earnings_history_lookback, _growth_read, _practitioner_readings, _quarterly_read, _rolling_average, _sequential_acceleration, _sequential_reading, _triple_acceleration, _yoy_growth
from .integrity import ACCOUNTING_INTEGRITY_WORDS, FMP_SOURCE, GOING_CONCERN_WORDS, _COST_CUTTING, _EARNINGS_QUALITY, _MARGIN_ANALYSIS, _ONE_TIME_INCOME, _RETURN_ON_EQUITY, _declared_status, _dilution_reading, _earnings_without_sales_growth, _fmp_discrepancies, _integrity_read, _inventory_receivables_vs_sales, _margin_read, _one_time_income_exclusion, _return_on_equity, _share_change_between
from .readings import LEADER_CATEGORIES, _ANNUAL_ONLY_FORMS, _ANNUAL_REQUIREMENT, _FOUR_FILED_QUARTERS, _HALF_QUARTER_DAYS, _MINIMUM_GROWTH, _MONTHS_PER_YEAR, _QUARTERS_PER_YEAR, _ROLLED_FORWARD, _accounting_basis, _adjacent, _anchored, _annual_only, _completed_months, _compound_growth, _consecutive_quarter_windows, _consecutive_tail, _current_tail, _dedupe, _eligible_filings, _growth_pct, _is_finite, _is_number, _latest_filed_period, _latest_periods, _leader_category, _measured_under, _merge_periods, _metric_series, _one_regime, _parse_date, _period_ordinal, _period_sort_key, _point, _practitioner_view, _previous_quarter, _previous_year_quarter, _prior_year, _provenance_conflict, _provenance_of, _quarter_ordinal_on, _reported, _require_source, _rolled_forward_windows, _spans_overlap, _trailing_twelve_months, _unread_claim
from .valuation import _ANTI_LOW_PE, _PE_EXPANSION, _PE_USELESS, _PE_VIEWS, _pe_expansion, _price_earnings, _trailing_share_base, _valuation


__all__ = []
