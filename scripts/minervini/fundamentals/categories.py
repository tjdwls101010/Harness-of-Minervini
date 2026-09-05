"""Category-specific fundamental readings."""

from __future__ import annotations

from typing import Any, Mapping
from .. import doctrine

from .growth import _annual_metric_growth
from .integrity import _share_change_between
from .readings import _compound_growth, _current_tail, _is_finite, _is_number, _measured_under, _metric_series, _period_ordinal, _prior_year, _reported, _trailing_twelve_months, _unread_claim


_TURNAROUND_GROWTH = "fundamentals.turnaround_growth_rate_threshold"
_TURNAROUND_CRITERIA = "fundamentals.turnaround_qualifying_criteria"
_MARKET_LEADER = "fundamentals.market_leader_earnings_growth_pace"
_INSTITUTIONAL_FAVORITE = "fundamentals.institutional_favorite_growth_pace"
_TOP_COMPETITOR = "fundamentals.top_competitor_reading"
_LAGGARD = "fundamentals.laggard_fundamentals_reading"
_CYCLICAL = "fundamentals.cyclical_inverse_pe_and_signals"


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
        "computability": doctrine.claim(_TURNAROUND_GROWTH)["computability"],
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
    trailing, peak, route = _trailing_twelve_months(quarterly["eps"], _metric_series(annual, "eps"), quarterly["latest_filed_period"])
    # Both figures are refused on the way out when the sums ran past what binary64 holds, so
    # comparing them there published a boolean computed from numbers the reading is not allowed
    # to show. `inf >= inf` is true, and it is not a company that got back to its old peak.
    at_or_above = None if not _is_finite(trailing) or not _is_finite(peak) else trailing >= peak
    return {
        "doctrine_id": _TURNAROUND_CRITERIA,
        "binds": doctrine.binds(_TURNAROUND_CRITERIA),
        "computability": doctrine.claim(_TURNAROUND_CRITERIA)["computability"],
        "strong_quarters": strong,
        "strong_means": _TURNAROUND_GROWTH,
        "gate": gate,
        "trailing_12m_eps": _reported(trailing),
        "trailing_12m_route": route,
        "trailing_12m_eps_prior_peak": _reported(peak),
        "trailing_12m_eps_at_or_above_prior_peak": at_or_above,
        "unquantified": ["near_prior_peak_is_unquantified"],
        # Either route satisfies it, and only one of the two is quantified. A trailing year
        # below its old peak has not failed "near or above" -- nobody in the corpus said how
        # near is near -- so this criterion can be satisfied or open and never refused. The
        # measured half is published beside it, which is the part a reader can act on.
        "satisfied": True if gate["state"] == "pass" or at_or_above is True else None,
    }


def _market_leader_reading(quarterly: Mapping[str, Any], annual: list[dict[str, Any]]) -> dict[str, Any]:
    """A market leader's annual pace, against the two figures the source gave for one.

    Twenty percent is a marker -- "they generally grow earnings at a rate of 20 percent or
    higher" names a value and declines to bound it -- so the reading is the measurement and its
    distance, never a pass. Thirty-five to forty-five is a band, and the source attached it to a
    best stretch of five or ten years, so it is measured over the best such stretch on file and
    reports unavailable when the filings do not reach back that far.
    """

    series = [(str(fact.get("period")), float(fact["eps"]), _measured_under(fact, "eps")) for fact in annual if _is_number(fact.get("eps"))]
    span, best, stretch_start, stretch_end = _best_stretch(series)
    reading = {
        "doctrine_id": _MARKET_LEADER,
        "binds": doctrine.binds(_MARKET_LEADER),
        "computability": doctrine.claim(_MARKET_LEADER)["computability"],
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


def _best_stretch(series: list[tuple[str, float, tuple[str | None, str | None]]]) -> tuple[int | None, float | None, str | None, str | None]:
    """The highest compound annual rate over any stretch the source's span covers.

    Consecutive years only. A stretch spanning a year the company did not file would compound
    across a gap and report the average of two eras as one company's best run.

    A company that grew at one rate for a decade ties with itself at every span the source's
    range covers, and the band reads the same whichever window wins. The tie goes to the fewest
    years the rate actually held -- the smallest claim the filings support -- because the span
    and periods published beside the rate are otherwise a field the reader cannot account for.
    """

    # "During their best 5- or 10-year stretch" names two lengths and none between them. Read
    # as a range it let a six-year window win, and the rate published under the source's own
    # 35-to-45 band was then measured over a span the source never mentioned.
    spans = [int(value) for value in doctrine.threshold(_MARKET_LEADER, "market_leader_best_stretch_years")]
    best: tuple[int | None, float | None, str | None, str | None] = (None, None, None, None)
    for span in sorted(spans):
        for position in range(len(series) - span):
            window = series[position:position + span + 1]
            ordinals = [_period_ordinal(point[0]) for point in window]
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
        "computability": doctrine.claim(_INSTITUTIONAL_FAVORITE)["computability"],
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

    # "Poised to rally" or "near the end" is a statement about now, so the rate it reads has to
    # be the latest filed quarter's or there is no direction to name.
    series = _current_tail(quarterly["eps_yoy_growth"], quarterly.get("latest_filed_period"))
    latest = series[-1]["yoy_pct"] if series else None
    direction = "unavailable" if latest is None else "rising" if latest > 0 else "falling" if latest < 0 else "flat"
    return {
        "doctrine_id": _CYCLICAL,
        "binds": doctrine.binds(_CYCLICAL),
        "computability": doctrine.claim(_CYCLICAL)["computability"],
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


_CATEGORY_READERS = {
    "turnaround": _turnaround_reading,
    "market_leader": lambda quarterly, annual: {"market_leader_earnings_growth_pace": _market_leader_reading(quarterly, annual)},
    "institutional_favorite": lambda quarterly, annual: {"institutional_favorite_growth_pace": _institutional_favorite_reading(quarterly, annual)},
    "cyclical": lambda quarterly, annual: {"cyclical_inverse_pe_and_signals": _cyclical_reading(quarterly, annual)},
    "top_competitor": _top_competitor_boundary,
    "past_leader_or_laggard": _laggard_boundary,
}
