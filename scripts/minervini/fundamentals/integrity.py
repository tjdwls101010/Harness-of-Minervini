"""Accounting integrity, dilution, margins and balance-sheet evidence."""

from __future__ import annotations

from datetime import date
import math
from typing import Any, Mapping
from .. import doctrine

from .readings import _adjacent, _consecutive_tail, _growth_pct, _is_number, _measured_under, _parse_date, _provenance_conflict, _reported, _require_source, _unread_claim


_EARNINGS_QUALITY = "fundamentals.inventory_receivables_vs_sales"
_MARGIN_ANALYSIS = "fundamentals.margin_analysis"
_COST_CUTTING = "fundamentals.cost_cutting_unsustainable"
_ONE_TIME_INCOME = "fundamentals.one_time_income_exclusion"
_RETURN_ON_EQUITY = "practitioners.fundamentals.minervini_roe_15_to_17_or_higher"
FMP_SOURCE = "fmp_enrichment"


# What an analyst may hand in beside the filings, because the filings do not carry it. The
# going-concern opinion and the audit's integrity finding live in the filing's narrative,
# which this harness does not read; the classification is a reading of the company's place
# in its industry, which no filing states at all.
GOING_CONCERN_WORDS = ("clear", "substantial_doubt")
ACCOUNTING_INTEGRITY_WORDS = ("clear", "concern", "restatement", "adverse")


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
    # A quarterly change is a change over one quarter. Across a hole in the filings the same
    # subtraction reports a year of dilution under a field name that says three months.
    if not _adjacent(quarters[-2].get("period"), quarters[-1].get("period")):
        return {"state": "unavailable", "reason": "no_adjacent_quarter_to_compare", "periods": [quarters[-2].get("period"), quarters[-1].get("period")]}
    previous, current = float(quarters[-2]["diluted_shares"]), float(quarters[-1]["diluted_shares"])
    if previous <= 0:
        return {"state": "unavailable", "reason": "share_count_is_not_a_count"}
    return {
        "state": "reported",
        "periods": [quarters[-2].get("period"), quarters[-1].get("period")],
        "quarterly_share_change_pct": _reported((current / previous - 1) * 100),
    }


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
        "computability": doctrine.claim(_COST_CUTTING)["computability"],
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


def _return_on_equity(annual: list[dict[str, Any]]) -> dict[str, Any]:
    """What a year's earnings returned on the equity that produced them.

    The source's use of it is comparative -- "use it to compare your stock with other stocks in
    the same industry group" -- and this evaluator holds one company, so half the claim is a
    named gap. The band is still measured, because fifteen to seventeen percent is a range the
    source gave as a range.

    Two of the practitioners in this corpus say they never look at it. The registry records that
    disagreement, and it travels with the reading rather than being resolved here.
    """

    claim = doctrine.claim(_RETURN_ON_EQUITY)
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
    income_from, equity_from = _measured_under(latest, "net_income"), _measured_under(latest, "stockholders_equity")
    if income_from != equity_from:
        # Which half differed decides what the reader does next, and one reason standing in for
        # the other is the same contradiction the annual pair had: a company reported as having
        # changed accounting regime when what changed was the currency.
        reason = "net_income_and_equity_measured_under_different_accounting_bases" if income_from[0] != equity_from[0] else "net_income_and_equity_measured_in_different_units"
        return {**reading, "state": "unavailable", "reason": reason, "period": latest.get("period"), "roe_pct": None, "band": doctrine.evaluate_band(_RETURN_ON_EQUITY, "roe_min", None)}
    equity = float(latest["stockholders_equity"])
    if equity <= 0:
        # A negative book value returns a ratio whose sign says the opposite of what it means:
        # a loss on negative equity comes out positive. It is refused rather than published.
        return {**reading, "state": "not_meaningful", "reason": "stockholders_equity_not_positive", "period": latest.get("period"), "roe_pct": None, "band": doctrine.evaluate_band(_RETURN_ON_EQUITY, "roe_min", None)}
    computed = float(latest["net_income"]) / equity * 100
    if not math.isfinite(computed):
        return {**reading, "state": "not_meaningful", "reason": "return_on_equity_beyond_arithmetic_range", "period": latest.get("period"), "roe_pct": None, "band": doctrine.evaluate_band(_RETURN_ON_EQUITY, "roe_min", None)}
    roe = _reported(computed)
    return {
        **reading,
        "state": "reported",
        "period": latest.get("period"),
        "net_income": _reported(float(latest["net_income"])),
        "stockholders_equity": _reported(equity),
        "roe_pct": roe,
        "band": doctrine.evaluate_band(_RETURN_ON_EQUITY, "roe_min", roe),
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
    # The same rule decision 281 settled for the margin: three growth rates divided into each
    # other mean nothing when the two years came from different books.
    conflict = _provenance_conflict(previous, latest, ("revenue", "inventory", "accounts_receivable"))
    if conflict:
        return {"doctrine_id": _EARNINGS_QUALITY, "state": "unavailable", "reason": conflict, "periods": [previous.get("period"), latest.get("period")]}
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
    # One gate, because the source stated one condition: "if receivables and inventories are
    # BOTH increasing at a greater rate than sales (twice or more)". Two gates applied the
    # combined limit to each balance on its own, so a company whose inventory ran ahead while
    # its receivables did not was published with a failing gate for a filter it had cleared.
    # The slower of the two is what the conjunction turns on.
    gate = doctrine.evaluate_gate(_EARNINGS_QUALITY, "receivables_and_inventory_vs_sales_double_trouble_ratio", min(both) if all(value is not None for value in both) else None)
    doubled = gate["state"] == "fail"
    # "Twice or more without explanation" -- and the explanation is management's, written in
    # prose this harness does not read. So the ratios say what they say and the source's own
    # phrase for the finding is not put on them, the same way the three footnote claims in
    # this evaluator publish the half they cannot reach rather than assuming it.
    return {
        **reading,
        **ratios,
        "state": "both_grew_at_least_twice_as_fast_as_sales" if doubled else "reported",
        "gate": gate,
        **({"missing_inputs": ["management_explanation_for_the_increase"]} if doubled else {}),
    }


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
