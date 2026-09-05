"""Growth measurements and source-defined comparisons."""

from __future__ import annotations

from typing import Any, Mapping
from .. import doctrine

from .integrity import _earnings_without_sales_growth, _margin_read, _share_change_between
from .readings import _ANNUAL_REQUIREMENT, _MINIMUM_GROWTH, _QUARTERS_PER_YEAR, _adjacent, _anchored, _compound_growth, _consecutive_tail, _current_tail, _is_number, _latest_filed_period, _measured_under, _metric_series, _period_ordinal, _point, _practitioner_view, _previous_quarter, _previous_year_quarter, _prior_year, _provenance_conflict, _provenance_of, _reported, _spans_overlap


_SUPERPERFORMANCE = "fundamentals.superperformance_quarterly_earnings_growth"
_BULL_MARKET = "fundamentals.bull_market_quarterly_earnings_growth"
_DECELERATION = "fundamentals.earnings_deceleration_red_flag"
_SMOOTHING = "fundamentals.two_quarter_rolling_average_smoothing"
_CODE_33 = "fundamentals.code_33_triple_acceleration"
_HISTORICAL_ACCELERATION = "fundamentals.earnings_acceleration_vs_historical_growth_rate"
_HISTORY_LOOKBACK = "fundamentals.earnings_history_lookback_window"
_ZANGER_GROWTH = "practitioners.earnings.zanger_min_30_to_40pct_gains_each_quarter_greater"
_SEQUENTIAL_ACCELERATION = "practitioners.earnings.minervini_accelerating_1_to_4_quarters"
_RITCHIE_GROWTH = "practitioners.earnings.ritchie_not_mechanical_explosive_growth_only"
MARKET_REGIMES = ("bull", "neutral", "bear")
_STALE_HEADLINE = "latest_filed_quarter_has_no_year_over_year_pair"


def _quarterly_read(quarters: list[dict[str, Any]], withheld: list[str] | None = None) -> dict[str, Any]:
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
        # The latest quarter the company filed, whatever it carried and whether or not it
        # survived. Every series above drops the quarters whose figure was absent, so reading
        # "the latest" off one of them made the quarter before an empty report into the
        # company's current quarter -- and a period withheld for reaching two closing dates
        # did the same thing while the envelope reported the collision beside it.
        "latest_filed_period": _latest_filed_period(quarters, withheld or []),
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
        if earlier is not None and _provenance_of(earlier) != _provenance_of(point):
            continue
        previous = None if earlier is None else earlier["value"]
        # A percentage change needs a base that means something. From a loss the arithmetic
        # still returns a number and that number has the wrong sign: a loss that doubled
        # comes out as plus one hundred percent, which cleared the growth range and reached
        # `supports_convergence` on evidence that says the opposite.
        if previous is not None and previous > 0:
            growth.append({"period": point["period"], "yoy_pct": _reported((point["value"] / previous - 1) * 100)})
    return growth



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
        "computability": doctrine.claim(_ANNUAL_REQUIREMENT)["computability"],
        "periods": [None if prior is None else prior["period"], None if latest is None else latest["period"]],
        "eps_yoy_pct": _annual_metric_growth(prior, latest, "eps"),
        "revenue_yoy_pct": _annual_metric_growth(prior, latest, "revenue"),
        **({"reason": "annual_periods_overlap"} if overlapping else {"reason": _provenance_conflict(prior, latest, ("eps", "revenue"))} if _provenance_conflict(prior, latest, ("eps", "revenue")) else {}),
    }


def _annual_metric_growth(prior: Mapping[str, Any] | None, latest: Mapping[str, Any] | None, metric: str) -> float | None:
    if prior is None or latest is None or not _is_number(prior.get(metric)) or not _is_number(latest.get(metric)):
        return None
    if _measured_under(prior, metric) != _measured_under(latest, metric):
        return None
    previous = float(prior[metric])
    if previous <= 0:
        return None
    return _reported((float(latest[metric]) / previous - 1) * 100)


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
    latest_filed = quarterly["latest_filed_period"]
    # Every reading below whose subject is the present state reads the anchored view. The
    # history lookback deliberately does not: its subject is the past one to two years, it
    # publishes the periods it examined, and eight quarters ending at the last measurable one
    # are still inside the window the source named.
    now = _anchored(quarterly, latest_filed)
    current = _current_tail(series, latest_filed)
    latest = current[-1]["yoy_pct"] if current else None
    superperformance = doctrine.evaluate_band(_SUPERPERFORMANCE, "superperformance_yoy_earnings_growth_percent", latest)
    readings = {
        "minimum_quarterly_earnings_growth": _banded_window(_MINIMUM_GROWTH, "minimum_yoy_earnings_growth_percent", "minimum_growth_window_quarters", series, latest_filed),
        "superperformance_quarterly_earnings_growth": superperformance if current else {**superperformance, "reason": _STALE_HEADLINE, "latest_filed_period": latest_filed},
        "bull_market_quarterly_earnings_growth": _bull_market_read(series, latest, market_regime, latest_filed),
        "earnings_deceleration": _deceleration_read(_current_tail(series, latest_filed)),
        "two_quarter_rolling_average": _rolling_average(now),
        "margin_trend": _margin_read(_current_tail(quarterly["margin_pct"], latest_filed)),
        "code_33_triple_acceleration": _code_33(now),
        "earnings_without_sales_growth": _earnings_without_sales_growth(now),
        "acceleration_vs_historical_growth_rate": _acceleration_vs_history(now, annual),
        "earnings_history_lookback": _earnings_history_lookback(quarterly),
        "practitioner_readings": _practitioner_readings(series, latest_filed),
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
        "computability": doctrine.claim(_CODE_33)["computability"],
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

    # Provenance travels with the endpoints. Stripping it before the compounding is the same
    # defect decision 281 closed for the margin, one step further from the filings: a US-GAAP
    # start compounded to an IFRS end reports a rate neither set of books contains.
    series = [(str(fact.get("period")), float(fact["eps"]), _measured_under(fact, "eps")) for fact in annual if _is_number(fact.get("eps"))]
    income = [(str(fact.get("period")), float(fact["net_income"]), _measured_under(fact, "net_income")) for fact in annual if _is_number(fact.get("net_income"))]
    three, three_reason, three_start = _compound_growth(series, 3)
    five, _, five_start = _compound_growth(series, 5)
    latest_period = series[-1][0] if series else None
    latest = quarterly["eps_yoy_growth"]
    reading = {
        "doctrine_id": _HISTORICAL_ACCELERATION,
        "binds": doctrine.binds(_HISTORICAL_ACCELERATION),
        "computability": doctrine.claim(_HISTORICAL_ACCELERATION)["computability"],
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


def _practitioner_readings(series: list[dict[str, Any]], latest_filed: str | None) -> dict[str, Any]:
    """The same quarterly growth, read the three other ways this corpus records.

    None of these can move a verdict. The canonical layer is the default and the practice layer
    fills execution gaps rather than overriding, so what these add is the disagreement itself --
    which a reader weighing a borderline measurement needs and cannot get from one voice.
    """

    current = _current_tail(series, latest_filed)
    band = doctrine.evaluate_band(_ZANGER_GROWTH, "yoy_quarterly_earnings_growth_target", current[-1]["yoy_pct"] if current else None)
    return {
        "zanger_quarterly_growth_target": {
            **_practitioner_view(_ZANGER_GROWTH),
            "band": band if current else {**band, "reason": _STALE_HEADLINE, "latest_filed_period": latest_filed},
        },
        "minervini_sequential_acceleration": {
            **_practitioner_view(_SEQUENTIAL_ACCELERATION),
            "lookback_quarters": doctrine.threshold(_SEQUENTIAL_ACCELERATION, "earnings_acceleration_lookback"),
            **(_sequential_reading(current) if current else {"state": "unavailable", "reason": _STALE_HEADLINE, "consecutive_accelerating_quarters": None}),
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
    current = _current_tail(series, latest_filed)
    reading = doctrine.evaluate_band(claim_id, band, current[-1]["yoy_pct"] if current else None)
    if not current:
        reading = {**reading, "reason": _STALE_HEADLINE, "latest_filed_period": latest_filed}
    # "The most recent three quarters" means three quarters in a row, ending where the filings
    # end. A window that reaches back over a quarter nobody filed reports the one before the gap
    # as though it were recent, and one anchored to a stale tail does the same a quarter later.
    held: list[dict[str, Any]] = []
    for length in range(quarters, 0, -1):
        tail = _consecutive_tail(current, length)
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
        "computability": doctrine.claim(_HISTORY_LOOKBACK)["computability"],
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
    # "The one before it" is the quarter before it, not whichever rate survived next to it in
    # the list. Over a hole in the filings that was a rate from two years ago called previous,
    # and a company growing faster every year came out decelerating.
    if not _adjacent(series[-2]["period"], series[-1]["period"]):
        return {"doctrine_id": _DECELERATION, "reason": "no_adjacent_quarter_to_compare", "periods": [series[-2]["period"], series[-1]["period"]], "latest_yoy_pct": series[-1]["yoy_pct"], "previous_yoy_pct": None, "decelerated": None}
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
