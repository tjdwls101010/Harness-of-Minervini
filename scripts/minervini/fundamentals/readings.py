"""Filed-period ordering, provenance and shared numeric readings."""

from __future__ import annotations

from datetime import date, timedelta
import math
from typing import Any, Mapping
from ..dates import parse_iso
from ..numbers import REPORTED_PRECISION as _REPORTED_PRECISION
from .. import doctrine




_MINIMUM_GROWTH = "fundamentals.minimum_quarterly_earnings_growth"
_ANNUAL_REQUIREMENT = "fundamentals.annual_earnings_requirement"
_MONTHS_PER_YEAR = 12
# The two annual-only foreign-issuer forms. Both carry a year and no quarters, so the three
# quarterly series are not a fetch that came up short.
_ANNUAL_ONLY_FORMS = ("20-F", "40-F")
_QUARTERS_PER_YEAR = 4
_FOUR_FILED_QUARTERS = "four_consecutive_filed_quarters"
_ROLLED_FORWARD = "annual_rolled_forward_by_filed_quarters"
# Half a quarter, used to ask which calendar quarter a fiscal year's closing date belongs to:
# the quarter that ends on it is the one whose middle sits this far behind it. Not a threshold
# -- it is the same midpoint rule the SEC provider labels a duration fact by.
_HALF_QUARTER_DAYS = 365 // (2 * _QUARTERS_PER_YEAR)
LEADER_CATEGORIES = ("market_leader", "top_competitor", "institutional_favorite", "turnaround", "cyclical", "past_leader_or_laggard")


def _require_source(evidence: Mapping[str, Any], expected: str, label: str) -> None:
    if evidence.get("source") != expected:
        raise ValueError(f"{label} evidence is required; web narrative cannot supply numeric facts.")


def _parse_date(value: Any, field: str) -> date:
    result = parse_iso(value)
    if result is None:
        raise ValueError(f"{field} must be an ISO date.")
    return result


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
            units = fact.get("_units") or {}
            for name in fact:
                if name not in {"period", "end", "_units"}:
                    # The unit belongs to the number as much as the regime does. SEC files a
                    # concept once per unit, and a hundred US dollars beside a hundred and
                    # thirty Canadian ones is not thirty percent of anything.
                    merged["_sources"][name] = {"accounting_basis": filing["accounting_basis"], "filed_at": filing["filed_at"], "unit": units.get(name)}
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


def _latest_filed_period(quarters: list[dict[str, Any]], withheld: list[str]) -> str | None:
    """The latest quarter the company filed, whether or not it survived the merge.

    A period withheld for reaching two closing dates is still a quarter that was filed, and
    dropping it here let the quarter before it become "the latest" -- so a trailing year a
    quarter out of date went out as `reported` while the envelope named the collision beside it.
    """

    names = [quarters[-1]["period"]] if quarters else []
    names += [name for name in withheld if isinstance(name, str)]
    ordered = [(name, _period_ordinal(name)) for name in names]
    return max(ordered, key=lambda pair: (pair[1] is not None, pair[1] or 0, pair[0]))[0] if ordered else None


def _provenance_of(point: Mapping[str, Any]) -> tuple[str | None, str | None]:
    """The regime and the unit a measured point carries, as one answer."""

    return point.get("accounting_basis"), point.get("unit")


def _measured_under(fact: Mapping[str, Any], metric: str) -> tuple[str | None, str | None]:
    """Under which regime and in which unit this one number was measured.

    A filer that changes regime carries both in one period, and decision 275 put provenance on
    the number rather than the period for exactly that reason. Every measurement built from two
    numbers has to ask this of both of them before their quotient or their difference means
    anything -- the margin was the only one asking.

    The unit rides along because the same question has the same answer for it: SEC stores a
    concept once per unit, and two currencies collapsed into one series produced growth rates
    out of an exchange rate nobody applied.
    """

    source = (fact.get("_sources") or {}).get(metric) or {}
    return source.get("accounting_basis", fact.get("accounting_basis")), source.get("unit")


def _point(fact: Mapping[str, Any], value: float, metric: str) -> dict[str, Any]:
    source = (fact.get("_sources") or {}).get(metric) or {"accounting_basis": fact["accounting_basis"], "filed_at": fact["filed_at"]}
    return {
        "period": fact["period"],
        "end": fact.get("end"),
        "value": value,
        # Both halves of the provenance, because both decide whether two of these can be
        # compared. Carrying only the regime let a reporting-currency change through as a
        # year of growth, and let a twelve-month sum add two currencies together.
        "accounting_basis": source["accounting_basis"],
        "unit": source.get("unit"),
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


def _spans_overlap(prior: Mapping[str, Any] | None, latest: Mapping[str, Any] | None) -> bool:
    """Whether two annual periods cover any of the same days.

    A fiscal-year change files a stub or a stretched year, and the year before it then runs
    into it. Their difference is not growth: part of it is the same months counted twice.
    """

    if prior is None or latest is None:
        return False
    ends, starts = prior.get("end"), latest.get("start")
    return isinstance(ends, str) and isinstance(starts, str) and ends >= starts


def _provenance_conflict(prior: Mapping[str, Any] | None, latest: Mapping[str, Any] | None, metrics: tuple[str, ...]) -> str | None:
    """Which of the two provenance questions refused this comparison, named separately.

    Both refuse, and they are not the same finding: one says the company changed accounting
    regime between the two years, the other that the two figures are in different currencies.
    One reason standing in for the other is a field disagreeing with the provenance printed
    beside it.
    """

    if prior is None or latest is None:
        return None
    for metric in metrics:
        before, after = _measured_under(prior, metric), _measured_under(latest, metric)
        if before[0] != after[0]:
            return "annual_periods_measured_under_different_accounting_bases"
        if before[1] != after[1]:
            return "annual_periods_measured_in_different_units"
    return None


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


def _previous_quarter(period: str) -> str:
    if "-Q" not in period:
        return ""
    year, quarter = period.rsplit("-Q", 1)
    try:
        year, quarter = int(year), int(quarter)
    except ValueError:
        return ""
    return f"{year - 1}-Q4" if quarter == 1 else f"{year}-Q{quarter - 1}"


def _compound_growth(series: list[tuple[str, float, tuple[str | None, str | None]]], years: int) -> tuple[float | None, str, str | None]:
    """A compound annual rate over ``years`` calendar years, or the reason there isn't one.

    The span is counted in years, not in rows. Reading three rows back lands on 2020 when the
    filings are 2020, 2022, 2024 and 2025, and calls a five-year span a three-year rate.

    Both endpoints must be positive. A negative or zero start describes a recovery from a loss
    as a growth rate, and a negative end sends the fractional power into the complex plane --
    which used to abort the whole capability with a TypeError on any loss-making filer.
    """

    if not series:
        return None, f"insufficient_annual_periods_for_a_{years}_year_rate", None
    by_period = {period: (value, measured) for period, value, measured in series}
    latest_period, end, end_measured = series[-1]
    latest = _period_ordinal(latest_period)
    if latest is None:
        return None, f"insufficient_annual_periods_for_a_{years}_year_rate", None
    start_period = str(latest - years)
    if start_period not in by_period:
        return None, f"insufficient_annual_periods_for_a_{years}_year_rate", None
    start, start_measured = by_period[start_period]
    if start_measured != end_measured:
        return None, "measured_under_different_accounting_bases", start_period
    if start <= 0 or end <= 0:
        return None, "compound_rate_requires_positive_endpoints", start_period
    return _reported(((end / start) ** (1 / years) - 1) * 100), "", start_period


def _trailing_twelve_months(series: list[dict[str, Any]], annual: list[dict[str, Any]] | None = None, latest_filed: str | None = None) -> tuple[float | None, float | None, str | None]:
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
    # denominator put a two-year-old earnings base under today's price. Which quarter that is
    # comes from the filings rather than from this series: a quarter filed without earnings
    # leaves the series a quarter short, and reading its tail put a December year under a May
    # price and called it reported.
    latest = latest_filed if latest_filed is not None else (series[-1]["period"] if series else None)
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

    return len({_provenance_of(point) for point in points}) <= 1


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


def _unread_claim(claim_id: str, missing_inputs: list[str], **extra: Any) -> dict[str, Any]:
    """A claim named with what it needed and did not get, rather than left out of the output.

    An omitted reading and an unrunnable one look the same to a reader, and only one of them is
    a boundary of what this capability does. These are not counted as per-request gaps: no
    filing was ever short of them.
    """

    return {
        "doctrine_id": claim_id,
        "binds": doctrine.binds(claim_id),
        "computability": doctrine.claim(claim_id)["computability"],
        "state": "not_evaluated",
        "missing_inputs": missing_inputs,
        **extra,
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


def _practitioner_view(claim_id: str) -> dict[str, Any]:
    """One practitioner's position, quoted rather than summarised.

    A judgment-only claim's whole content is the sentence somebody said. Paraphrasing it would
    put this harness's words under their name, and these are exactly the claims where the
    difference between "never looks at it" and "rarely concerns himself with it" is the point.
    """

    record = doctrine.claim(claim_id)
    return {
        "doctrine_id": claim_id,
        "attributed_to": record["attributed_to"],
        "binds": doctrine.binds(claim_id),
        "computability": record["computability"],
        "quotation": doctrine.quotation(claim_id),
    }


def _is_finite(value: Any) -> bool:
    """A number the arithmetic produced and can still be compared."""

    return _is_number(value) and math.isfinite(float(value))


def _adjacent(earlier: Any, later: Any) -> bool:
    """Whether the second period is the one immediately after the first."""

    ordinals = (_period_ordinal(earlier), _period_ordinal(later))
    return None not in ordinals and ordinals[1] - ordinals[0] == 1


def _anchored(quarterly: Mapping[str, Any], latest_filed: str | None) -> dict[str, Any]:
    """The quarterly series, each cut back to nothing unless it still reaches the latest filing.

    One helper answers "does this series still speak about now" and every reading whose subject
    is the present state asks it. Passing the raw series instead left Code 33, the margin trend,
    the smoothed pair and the deceleration flag all describing a quarter the company has since
    filed past.
    """

    return {name: (_current_tail(value, latest_filed) if isinstance(value, list) else value) for name, value in quarterly.items()}


def _current_tail(series: list[dict[str, Any]], latest_filed: str | None) -> list[dict[str, Any]]:
    """The series, but only while it still reaches the quarter the company last filed.

    Every series here drops the quarters whose own figure was absent, so a quarter filed
    without earnings leaves the earnings series ending a quarter earlier. Reading "the latest"
    off it then promotes a stale quarter to the company's current one -- and a window of "the
    most recent three quarters" slides back with it, over a quarter that has since been filed.
    """

    return series if series and latest_filed is not None and series[-1]["period"] == latest_filed else []


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


def _is_number(value: Any) -> bool:
    """A value the arithmetic here can use, which excludes the two floats that are not numbers.

    `nan` and the infinities pass every isinstance check, survive every comparison as False,
    and then break strict JSON encoding at the envelope -- after a reading has already been
    published beside them saying it was measured.
    """

    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
