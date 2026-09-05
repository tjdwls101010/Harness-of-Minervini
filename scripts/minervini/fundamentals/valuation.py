"""Trailing multiples and valuation expansion evidence."""

from __future__ import annotations

from datetime import date
import math
from typing import Any, Mapping
from .. import doctrine

from .readings import _completed_months, _eligible_filings, _is_number, _latest_filed_period, _latest_periods, _merge_periods, _metric_series, _parse_date, _practitioner_view, _reported, _trailing_twelve_months, _unread_claim


_PE_USELESS = "fundamentals.pe_useless_alone"
_ANTI_LOW_PE = "fundamentals.anti_low_pe_bargain_trap"
_PE_EXPANSION = "fundamentals.pe_expansion_late_stage_and_historical_average"
_PE_VIEWS = ("practitioners.fundamentals.minervini_pe_indifferent_prefers_high_over_ultralow", "practitioners.fundamentals.ritchie_never_pe")


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

    trailing, _, route = _trailing_twelve_months(quarterly["eps"], _metric_series(annual, "eps"), quarterly["latest_filed_period"])
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
    # The inputs are finite and the quotient need not be. `_reported` turns the infinity into a
    # null on the way out, which is right -- but the state was chosen before it, so the block
    # said `reported` and carried no ratio, which reads like a number the filings never had.
    ratio = float(last_close) / trailing
    if not math.isfinite(ratio):
        return {**reading, "state": "not_meaningful", "reason": "price_earnings_ratio_beyond_arithmetic_range", "pe_ratio": None}
    return {**reading, "state": "reported", "pe_ratio": _reported(ratio)}


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

    reading = {"doctrine_id": _PE_EXPANSION, "binds": doctrine.binds(_PE_EXPANSION), "computability": doctrine.claim(_PE_EXPANSION)["computability"]}
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
    # The same question at the breakout, asked of the filings that existed then: the latest
    # quarter filed by that date, not the latest one carrying an earnings figure.
    quarters_then, withheld_then = _merge_periods(known, "quarterly")
    at_breakout, _, at_breakout_route = _trailing_twelve_months(_metric_series(quarters_then, "eps"), _metric_series(_latest_periods(known, "annual"), "eps"), _latest_filed_period(quarters_then, withheld_then))
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
        # The study's average, beside this stock's expansion and never compared with it. "On
        # average (or two to three times)" describes what superperformance stocks did as a
        # population, so a positional state against it said this ticker sat inside a range that
        # was never a standard. The conditional half of the same passage is the band above.
        "multiple_measured": None if expanded is None else _reported(expanded),
        "historical_average_multiple": doctrine.threshold(_PE_EXPANSION, "pe_expansion_historical_average_multiple"),
        "elapsed": doctrine.evaluate_band(_PE_EXPANSION, "pe_expansion_signal_window_months", months),
    }
