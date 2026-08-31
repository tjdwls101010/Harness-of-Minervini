"""Pure adapters for the evidence consumed by :mod:`scripts.minervini.market`.

The adapters deliberately preserve source observations.  They do not assign a
bullish or bearish breadth reading, infer leader behavior from RS rank, or make
a weighted group score.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, datetime
from html.parser import HTMLParser
import math
import re
from typing import Any

from . import doctrine
from .windows import year_window_start


_FINVIZ_SECTIONS = (
    ("advancing_declining", "advancing", "declining"),
    ("new_high_low", "new_high", "new_low"),
    ("sma50", "above", "below"),
    ("sma200", "above", "below"),
)
_GROUP_NEW_HIGHS = "market.group_new_highs_signal"
_GROUP_MEMBER_READING = "convention.group_member_reading"
_TRADING_WEEK = "convention.trading_week"
_STRIKING_DISTANCE = "market.striking_distance_52w_high"
_LOW_LIST = "market.avoid_52w_low_list"
_CORRECTION_DEPTH = "market.correction_depth_healthy_leader"
_PCT_COUNT = re.compile(r"(?P<pct>\d+(?:\.\d+)?)%\s*\(\s*(?P<count>[\d,]+)\s*\)")
_COUNT_PCT = re.compile(r"\(\s*(?P<count>[\d,]+)\s*\)\s*(?P<pct>\d+(?:\.\d+)?)%")


class _FinvizMarketStatsParser(HTMLParser):
    """Collect left and right text from Finviz market-stat blocks natively."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.sections: list[dict[str, list[str]]] = []
        self._elements: list[tuple[dict[str, list[str]] | None, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = set((dict(attrs).get("class") or "").split())
        parent = next((section for section, _ in reversed(self._elements) if section is not None), None)
        section = parent
        if tag == "div" and "market-stats" in classes:
            section = {"left": [], "right": []}
            self.sections.append(section)
        side = None
        if section is not None:
            if "market-stats_labels_left" in classes:
                side = "left"
            elif "market-stats_labels_right" in classes:
                side = "right"
        self._elements.append((section, side))

    def handle_endtag(self, tag: str) -> None:
        if self._elements:
            self._elements.pop()

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text:
            return
        for section, side in reversed(self._elements):
            if section is not None and side is not None:
                section[side].append(text)
                return


def build_market_evidence(
    *,
    qqq_daily_ohlcv: Iterable[Mapping[str, Any]] | None,
    finviz_html: str | None,
    sector_rows: Iterable[Mapping[str, Any]] | None,
    industry_rows: Iterable[Mapping[str, Any]] | None,
    leader_rows: Iterable[Mapping[str, Any]] | None,
    trade_traction: Any,
    leader_history: Mapping[str, Any] | None = None,
    leader_groups: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert completed source snapshots to ``evaluate_market_snapshot`` input.

    ``trade_traction`` intentionally has no default: it is user feedback, never
    an inference from market, Finviz, or RS data.
    """
    history = leader_history or {}
    leaders = _leader_evidence(leader_rows, history, leader_groups)
    return {
        "breadth": _finviz_breadth(finviz_html),
        "qqq_21ema": _qqq_21ema_switch(qqq_daily_ohlcv),
        "sectors": _group_evidence(sector_rows, "sector", leaders, history, leader_groups),
        "industries": _group_evidence(industry_rows, "industry", leaders, history, leader_groups),
        "leaders": leaders,
        "trade_traction": trade_traction,
    }


def _finviz_breadth(document: str | None) -> dict[str, Any]:
    if document is None:
        return _unavailable_breadth("finviz_html_missing")
    if not isinstance(document, str):
        return _unavailable_breadth("finviz_html_invalid")

    parser = _FinvizMarketStatsParser()
    try:
        parser.feed(document)
        parser.close()
    except Exception as error:
        return _unavailable_breadth(f"finviz_html_unparseable:{type(error).__name__}")

    by_name: dict[str, list[dict[str, list[str]]]] = {name: [] for name, _, _ in _FINVIZ_SECTIONS}
    for block in parser.sections:
        section_name = _finviz_section_name(block)
        if section_name is not None:
            by_name[section_name].append(block)

    sections: dict[str, dict[str, Any]] = {}
    for section_name, positive_name, negative_name in _FINVIZ_SECTIONS:
        matches = by_name[section_name]
        if not matches:
            sections[section_name] = _unavailable("finviz_section_missing")
            continue
        if len(matches) > 1:
            sections[section_name] = _unavailable("finviz_section_duplicate")
            continue
        parsed = _finviz_section(matches[0], positive_name, negative_name)
        sections[section_name] = parsed
    return {
        "state": "observed" if any(section["state"] == "observed" for section in sections.values()) else "unavailable",
        "sections": sections,
    }


def _unavailable_breadth(reason: str) -> dict[str, Any]:
    return {
        "state": "unavailable",
        "sections": {name: _unavailable(reason) for name, _, _ in _FINVIZ_SECTIONS},
    }


def _finviz_section(section: Mapping[str, list[str]], positive_name: str, negative_name: str) -> dict[str, Any]:
    positive = _finviz_side(section.get("left", []), _PCT_COUNT)
    negative = _finviz_side(section.get("right", []), _COUNT_PCT)
    if positive is None or negative is None:
        return _unavailable("finviz_section_malformed")
    return {"state": "observed", positive_name: positive, negative_name: negative}


def _finviz_section_name(section: Mapping[str, list[str]]) -> str | None:
    labels = " ".join((*section.get("left", []), *section.get("right", []))).casefold()
    if "advanc" in labels and "declin" in labels:
        return "advancing_declining"
    if re.search(r"new\s+high", labels) and re.search(r"new\s+low", labels):
        return "new_high_low"
    if _sma_label(labels, 50):
        return "sma50"
    if _sma_label(labels, 200):
        return "sma200"
    return None


def _sma_label(labels: str, period: int) -> bool:
    return bool(
        re.search(rf"\b{period}\s*(?:day\s*)?sma\b", labels)
        or re.search(rf"\bsma\s*{period}\b", labels)
    ) and "above" in labels and "below" in labels


def _finviz_side(texts: Iterable[str], pattern: re.Pattern[str]) -> dict[str, float | int] | None:
    for text in texts:
        match = pattern.search(text)
        if match:
            return {"pct": float(match.group("pct")), "count": int(match.group("count").replace(",", ""))}
    return None


def _qqq_21ema_switch(bars: Iterable[Mapping[str, Any]] | None) -> dict[str, Any]:
    if bars is None:
        return _unavailable("qqq_daily_ohlcv_missing")
    try:
        completed = list(bars)
    except TypeError:
        return _unavailable("qqq_daily_ohlcv_invalid")
    if len(completed) < 22:
        return _unavailable("qqq_completed_sessions_insufficient")

    dates: list[str] = []
    closes: list[float] = []
    lows: list[float] = []
    for row in completed:
        if not isinstance(row, Mapping) or row.get("completed") is False:
            return _unavailable("qqq_daily_ohlcv_not_completed")
        date_value = row.get("date", row.get("Date"))
        close = _finite_number(row.get("close", row.get("Close")))
        low = _finite_number(row.get("low", row.get("Low")))
        if date_value is None or close is None or low is None:
            return _unavailable("qqq_daily_ohlcv_malformed")
        date_text = str(date_value)
        if dates and date_text <= dates[-1]:
            return _unavailable("qqq_daily_ohlcv_not_ordered")
        dates.append(date_text)
        closes.append(close)
        lows.append(low)

    alpha = 2 / 22
    ema_values = [closes[0]]
    for close in closes[1:]:
        ema_values.append(alpha * close + (1 - alpha) * ema_values[-1])

    state = "unknown"
    transition_reason: str | None = None
    last_transition: str | None = None
    transitions: list[dict[str, str]] = []
    for index in range(20, len(closes)):
        close = closes[index]
        ema = ema_values[index]
        next_state = state
        reason = None
        if close > ema:
            next_state = "on"
            reason = "one completed close above the 21 EMA"
        elif index > 20 and closes[index - 1] < ema_values[index - 1] and close < ema and close < lows[index - 1]:
            next_state = "off"
            reason = "two closes below the 21 EMA and the second close below the prior day's low"
        if next_state != state and next_state != "unknown":
            last_transition = dates[index]
            transition_reason = reason
            transitions.append({"date": dates[index], "state": next_state, "reason": str(reason)})
        state = next_state

    return {
        "state": state,
        "date": dates[-1],
        "close": round(closes[-1], 4),
        "ema21": round(ema_values[-1], 4),
        "prior_close": round(closes[-2], 4),
        "prior_low": round(lows[-2], 4),
        "last_transition": last_transition,
        "transition_reason": transition_reason,
        "recent_transitions": transitions[-5:],
        "rules": {
            "ON": "one completed close above the 21 EMA",
            "OFF": "two closes below the 21 EMA and the second close below the prior day's low",
        },
    }


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _group_evidence(
    rows: Iterable[Mapping[str, Any]] | None,
    group_type: str,
    leaders: list[dict[str, Any]] | None,
    history: Mapping[str, Any],
    groups_read: Mapping[str, Any] | None,
) -> list[dict[str, Any]] | None:
    """Each ranked group, read through the market's ranked leaders that fall inside it.

    The RS source publishes a group average and a member count, and no membership at all, so
    the names a group can be read through are the leaders the snapshot already fetched. That
    is a sample and never a census, which is why every count here is published beside the
    names it was taken over.

    A word the caller put in the source row is no longer read. Five of the six slots this
    replaces were permanently unavailable and the sixth reported `observed` off the presence
    of a rating -- a placeholder that made a leaderless group and a measured one look alike.
    """

    if rows is None:
        return None
    if isinstance(rows, (str, bytes, Mapping)):
        return None
    result: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            continue
        name = str(row.get("name") or row.get(group_type) or row.get("id") or f"{group_type}-{index + 1}")
        sample = _group_member_sample(name, group_type, leaders, history, groups_read)
        result.append(
            {
                "name": name,
                "basis": _basis(row),
                "member_sample": sample,
                "new_highs": _group_new_highs(sample, history, group_type),
                "striking_distance_names": _group_striking_distance(sample, leaders),
                "source_row": dict(row),
            }
        )
    return result


def _group_member_sample(
    name: str,
    group_type: str,
    leaders: list[dict[str, Any]] | None,
    history: Mapping[str, Any],
    groups_read: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Which ranked leaders sit in this group, and which of them have a window to count over.

    Classification is a current snapshot the provider refuses for a past session, so "nobody
    was classified" and "this group holds none of the leaders" are different answers and are
    reported as different reasons.
    """

    empty: dict[str, Any] = {"ranked_leaders_in_group": [], "not_counted": [], "unclassified": []}
    if groups_read is None:
        return {"state": "unavailable", "reason": "leader_classification_not_read", **empty}
    members: list[str] = []
    not_counted: list[dict[str, str]] = []
    unclassified: list[str] = []
    for ticker in _unique_tickers(leaders):
        classification = groups_read.get(ticker)
        if not isinstance(classification, Mapping):
            unclassified.append(ticker)
            continue
        if str(classification.get(group_type, "")).casefold() != name.casefold():
            continue
        members.append(ticker)
        if _countable_window(history.get(ticker)) is None:
            not_counted.append({"ticker": ticker, "reason": "completed_sessions_insufficient"})
    if not members:
        # A leader nobody could classify may well belong here, so "no member" is only an
        # answer when every ranked leader was placed. Otherwise the group has a gap, and a
        # gap reported as an absence is missing evidence published as negative evidence.
        reason = "no_ranked_leader_in_this_group" if not unclassified else "classification_incomplete_for_the_ranked_leaders"
        return {"state": "unavailable", "reason": reason, **{**empty, "unclassified": unclassified}}
    return {"state": "reported", "ranked_leaders_in_group": members, "not_counted": not_counted, "unclassified": unclassified}


def _unique_tickers(leaders: list[dict[str, Any]] | None) -> list[str]:
    """Each ranked ticker once. A source that prints one name twice must not count it twice."""

    seen: set[str] = set()
    tickers: list[str] = []
    for leader in leaders or []:
        ticker = leader.get("ticker")
        if isinstance(ticker, str) and ticker not in seen:
            seen.add(ticker)
            tickers.append(ticker)
    return tickers


def _group_new_highs(sample: Mapping[str, Any], history: Mapping[str, Any], group_type: str) -> dict[str, Any]:
    """How many of the group's ranked names print a new 52-week high now against one window ago.

    The source states the signal as a direction -- a growing number of names making new highs
    -- and names no window to measure the growth over, so the length comes from the registry
    rather than from this module.
    """

    reading = {
        "doctrine_id": _GROUP_NEW_HIGHS,
        "binds": doctrine.binds(_GROUP_NEW_HIGHS),
        # The claim states the signal; the two conventions below sized the window it is read
        # over, and a reader following the citation needs all three to arrive at this count.
        "window_doctrine_ids": [_GROUP_MEMBER_READING, _TRADING_WEEK],
    }
    if group_type != "industry":
        # "a growing number of names in a particular industry" -- the source scoped this
        # signal to an industry, and a sector is not one. Publishing the same count for a
        # sector would put the claim's name on a measurement it never described.
        return {**reading, "state": "not_applicable", "reason": "the_source_states_this_signal_for_an_industry"}
    lookback = _growth_lookback_sessions()
    countable = [ticker for ticker in sample.get("ranked_leaders_in_group", []) if _countable_window(history.get(ticker)) is not None]
    if not countable:
        return {**reading, "state": "unavailable", "reason": sample.get("reason") or "no_ranked_leader_with_a_full_window"}
    now = sum(1 for ticker in countable if _at_new_high(history[ticker], 0))
    earlier = sum(1 for ticker in countable if _at_new_high(history[ticker], lookback))
    return {
        **reading,
        "state": "supports" if now > earlier else "observed",
        "measured": {"now": now, "earlier": earlier, "of_names_read": len(countable), "lookback_sessions": lookback},
    }


def _group_striking_distance(sample: Mapping[str, Any], leaders: list[dict[str, Any]] | None) -> dict[str, Any]:
    """How many of the group's ranked names sit inside the source's striking-distance range.

    A count of names inside a range is not itself a range reading, so this reports the count
    and the sample it came from and never a pass.
    """

    reading = {
        "doctrine_id": _STRIKING_DISTANCE,
        "binds": doctrine.binds(_STRIKING_DISTANCE),
        # The claim states a per-stock distance. What licenses counting it across a group is
        # the convention that defined the sample, so the count cites both or neither.
        "sample_doctrine_ids": [_GROUP_MEMBER_READING],
    }
    members = set(sample.get("ranked_leaders_in_group", []))
    if not members:
        return {**reading, "state": "unavailable", "reason": sample.get("reason") or "no_ranked_leader_in_this_group"}
    states = [
        leader.get("distance_from_52w_high", {}).get("state")
        for leader in leaders or []
        if leader.get("ticker") in members
    ]
    read = [state for state in states if state not in {None, "unavailable"}]
    if not read:
        return {**reading, "state": "unavailable", "reason": "leader_price_history_not_read"}
    return {
        **reading,
        "state": "reported",
        "measured": {"within_source_range": sum(1 for state in read if state == "within_source_range"), "of_names_read": len(read)},
    }


def _growth_lookback_sessions() -> int:
    weeks = doctrine.parameter(_GROUP_MEMBER_READING, "new_high_growth_lookback_weeks")
    return int(weeks) * _sessions_per_week()


def _sessions_per_week() -> int:
    return int(doctrine.parameter(_TRADING_WEEK, "sessions_per_trading_week"))


def _countable_window(bars: Any) -> tuple[list[float], list[float], list[float], list[date]] | None:
    """The name's series, but only when a full year stands behind the earlier count too.

    Both ends of the growth reading are 52-week highs, so both need a 52-week window behind
    them. Requiring one only at the latest session would compare a measured high with one
    taken over however many bars happened to precede it.
    """

    closes, _opens, highs, lows, dates = _leader_series(bars)
    if closes is None or dates is None:
        return None
    earlier = len(highs) - 1 - _growth_lookback_sessions()
    if year_window_start(dates, earlier) is None:
        return None
    return closes, highs, lows, dates


def _at_new_high(bars: Any, sessions_ago: int) -> bool:
    """Was this name's high, that many completed sessions back, the highest of its trailing year?"""

    window = _countable_window(bars)
    if window is None:
        return False
    _, highs, _, dates = window
    index = len(highs) - 1 - sessions_ago
    start = year_window_start(dates, index)
    if start is None:
        return False
    return highs[index] >= max(highs[start : index + 1])


def _leader_evidence(
    rows: Iterable[Mapping[str, Any]] | None, history: Mapping[str, Any], groups_read: Mapping[str, Any] | None = None
) -> list[dict[str, Any]] | None:
    """Each ranked leader, with what its own completed bars say about how it is behaving.

    The RS source ranks tickers and says nothing about behavior, so this used to stand a
    placeholder in that slot -- and a placeholder reports `observed`, which is not `supports`.
    The favorable regime was therefore unreachable from any live snapshot, not because the
    market never qualified but because one of its four signals could never be met.

    A caller-supplied behavior word is no longer read where the bars can answer. It was the same
    shape as the going-concern field the fundamentals evaluator used to read off a provider that
    never sent it: a verdict input with no evidence under it.
    """

    if rows is None:
        return None
    if isinstance(rows, (str, bytes, Mapping)):
        return None
    leaders: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        basis = _basis(row)
        ticker = row.get("ticker")
        if isinstance(ticker, str):
            if ticker in seen:
                continue
            seen.add(ticker)
        classification = (groups_read or {}).get(ticker) if isinstance(ticker, str) else None
        leaders.append(
            {
                "ticker": ticker,
                **_leader_price_behavior(history.get(ticker) if isinstance(ticker, str) else None),
                "group": dict(classification) if isinstance(classification, Mapping) else None,
                "basis": basis,
                "source_row": dict(row),
            }
        )
    return leaders


def _leader_price_behavior(bars: Any) -> dict[str, Any]:
    """The three deterministic things this corpus says about a leader's own price.

    How far it sits from a new 52-week high, whether it is printing on the 52-week-low list, and
    how deep its correction has run. The band never carries the state alone: the depth's own
    gate is the only reading here that can refuse, and the source's instruction about the low
    list is a filter it stated outright.

    Nothing is published until a full 52-week window has completed. A high taken over two bars
    is not a 52-week high, and reporting one is the shape of fabrication this harness exists to
    refuse -- the reader cannot tell a measured 3% from a 3% measured over a fortnight.

    The window is the one the whole harness uses: bounded by date rather than by a bar count,
    so a name whose sessions were thinned by a halt cannot reach past the year for its high.
    """

    closes, opens, highs, lows, dates = _leader_series(bars)
    if closes is None:
        return _unreadable_leader("leader_price_history_not_read")
    if dates is None:
        return _unreadable_leader("leader_price_history_carries_no_session_dates")
    start = year_window_start(dates, len(closes) - 1)
    if start is None:
        return _unreadable_leader("completed_sessions_short_of_a_52_week_window")
    window = slice(start, None)
    last, high_52w = closes[-1], max(highs[window])
    distance = doctrine.evaluate_band(_STRIKING_DISTANCE, "striking_distance_from_52w_high", _reported((high_52w - last) / high_52w * 100) if high_52w > 0 else None)
    # What puts a ticker on the 52-week-low list is its own low being made now, so the reading
    # is whether this session printed the lowest low of the window. Comparing the close with
    # that low instead answered yes only when the close happened to equal the session's low.
    on_low_list = {"doctrine_id": _LOW_LIST, "binds": doctrine.binds(_LOW_LIST), "state": "reported", "measured": bool(lows[-1] <= min(lows[window]))}
    depth = _correction_depth(opens[window], highs[window], lows[window])
    correction = doctrine.evaluate_band(_CORRECTION_DEPTH, "healthy_correction_range", depth)
    gate = doctrine.evaluate_gate(_CORRECTION_DEPTH, "correction_failure_threshold", depth)
    return {
        "behavior": _leader_behavior_state(distance, on_low_list, gate),
        "distance_from_52w_high": distance,
        "on_52w_low_list": on_low_list,
        "correction_depth": correction,
        "correction_gate": gate,
    }


def _unreadable_leader(reason: str) -> dict[str, Any]:
    return {
        "behavior": {"state": "unavailable", "reason": reason},
        "distance_from_52w_high": doctrine.evaluate_band(_STRIKING_DISTANCE, "striking_distance_from_52w_high", None),
        "on_52w_low_list": {"doctrine_id": _LOW_LIST, "binds": doctrine.binds(_LOW_LIST), "state": "unavailable", "measured": None},
        "correction_depth": doctrine.evaluate_band(_CORRECTION_DEPTH, "healthy_correction_range", None),
        "correction_gate": doctrine.evaluate_gate(_CORRECTION_DEPTH, "correction_failure_threshold", None),
    }


def _leader_behavior_state(distance: Mapping[str, Any], on_low_list: Mapping[str, Any], gate: Mapping[str, Any]) -> dict[str, Any]:
    """One state from a gate and a band, in that order of authority.

    A band cannot carry a verdict alone, so nearness to a new high supports only alongside a
    correction the source's own ceiling did not refuse. The low list is a filter the source
    stated outright -- "stay away from this list and all of its components" -- so it contradicts
    on its own.
    """

    if on_low_list.get("measured") is True:
        return {"state": "contradicts", "reason": "printing_on_the_52_week_low_list"}
    if gate.get("state") == "fail":
        return {"state": "contradicts", "reason": "correction_deeper_than_the_source_ceiling"}
    if gate.get("state") == "pass" and distance.get("state") in {"within_source_range", "below_source_range"}:
        return {"state": "supports"}
    if distance.get("state") in {None, "unavailable"} or gate.get("state") in {None, "unavailable"}:
        return {"state": "unavailable", "reason": "leader_price_history_not_read"}
    return {"state": "observed"}


def carries_a_readable_bar(bars: Any) -> bool:
    """Whether these rows yield the series every leader reading is taken from.

    The caller that collects a leader's history has to report a gap when the reading was never
    taken, and "the frame was empty" is only one way for that to happen: a frame of three
    hundred rows carrying no price at all publishes exactly as little. Both callers ask the
    same question here so that the envelope's gap and the payload's `unavailable` cannot come
    from two different definitions of readable.
    """

    return _leader_series(bars)[0] is not None


def _leader_series(bars: Any) -> tuple[list[float] | None, list[float | None], list[float], list[float], list[date] | None]:
    """Closes, opens, highs, lows and session dates from completed rows, or nothing at all.

    A history with one unreadable row is not a history with a hole to work around: every
    measurement below reads the whole window, so a partial read would report a 52-week high the
    ticker may never have printed. Order is checked because every index here assumes oldest to
    newest, and a newest-first frame would report the oldest close as today's -- the same check
    the index block a few lines up has always made. A non-positive price is refused rather than
    divided by: a low of zero reports a hundred-percent correction on a stock that never moved.

    The open is the exception the close, high and low are not: a bar missing it is still a
    readable bar, because only the correction depth reads the open and it falls back cleanly.
    So a missing or non-positive open becomes None for that bar rather than voiding the series.

    Dates come back too, and a history missing or misspelling one comes back with none at all
    rather than with the dates it happened to have: what reads them is the 52-week window, and
    a window bounded by the dates of some of its bars is not the window it says it is. The
    prices are still returned, because a reading that does not ask what year it is -- there
    are none here today -- would otherwise lose a series it could have used.
    """

    if bars is None:
        return None, [], [], [], None
    try:
        rows = list(bars)
    except TypeError:
        return None, [], [], [], None
    closes: list[float] = []
    opens: list[float | None] = []
    highs: list[float] = []
    lows: list[float] = []
    dates: list[date] | None = []
    for row in rows:
        if not isinstance(row, Mapping) or row.get("completed") is False:
            return None, [], [], [], None
        close = _finite_number(row.get("close", row.get("Close")))
        high = _finite_number(row.get("high", row.get("High")))
        low = _finite_number(row.get("low", row.get("Low")))
        if close is None or high is None or low is None:
            return None, [], [], [], None
        if min(close, high, low) <= 0:
            return None, [], [], [], None
        opened = _finite_number(row.get("open", row.get("Open")))
        date_value = row.get("date", row.get("Date"))
        if date_value is None:
            # A row that never claimed a date is a row the window readings cannot use. The
            # prices are still a series, so they are kept and the dates are dropped whole.
            dates = None
        else:
            stamp = _session_date(date_value)
            if stamp is None:
                # A date that is there and unreadable is a broken bar, not an undated one,
                # and a broken bar voids the history the way an unreadable price does.
                return None, [], [], [], None
            if dates is not None:
                if dates and stamp <= dates[-1]:
                    # Every index here assumes oldest to newest, and a newest-first frame
                    # would report the oldest close as today's.
                    return None, [], [], [], None
                dates.append(stamp)
        closes.append(close)
        opens.append(opened if opened is not None and opened > 0 else None)
        highs.append(high)
        lows.append(low)
    if not closes:
        return None, [], [], [], None
    return closes, opens, highs, lows, dates


def _session_date(value: Any) -> date | None:
    """One session's calendar date, or nothing when what the row carried is not one."""

    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _correction_depth(opens: list[float | None], highs: list[float], lows: list[float]) -> float | None:
    """The deepest decline from a peak to a low that came after it, anywhere in the window.

    Measuring from the window's highest high erased the very correction the claim is about:
    the source's ceiling decides whether a stock is buyable "on the next new high", so a stock
    that just made one reported a depth of zero and the reading became unreachable exactly
    where it was needed. Running the peak forward also settles what an argmax could not --
    which of two tied peaks to anchor on.

    A daily bar never records whether its high or its low printed first, so a session's low is
    never measured against its own high: a bar that opened low, sold off, and then ran to a new
    high did not decline across its whole span, and reading it that way invents an ordering no
    completed bar states. But the bar does record one order -- the open prints before both. So
    the peak a low is measured against is the highest of the sessions before it and this bar's
    own open, and never this bar's high. When the open is itself a new peak, the open-to-low
    decline is one the completed bar states outright; when no open was read, the low falls back
    to the peak the earlier sessions established.
    """

    if not highs or not lows:
        return None
    peak: float | None = None
    deepest = 0.0
    for opened, high, low in zip(opens, highs, lows):
        anchor = peak
        if opened is not None and opened > 0:
            anchor = opened if anchor is None else max(anchor, opened)
        if anchor is not None and anchor > 0:
            deepest = max(deepest, (anchor - low) / anchor * 100)
        peak = high if peak is None else max(peak, high)
    return _reported(deepest)


def _reported(value: float | None) -> float | None:
    return None if value is None or not math.isfinite(value) else round(value, 10)


def _basis(row: Mapping[str, Any]) -> dict[str, Any]:
    basis: dict[str, Any] = {}
    if row.get("as_of") is not None:
        basis["as_of"] = row["as_of"]
    rating = row.get("rating", row.get("rs_rating"))
    if rating is not None:
        basis["rating"] = rating
    rank = row.get("rank", row.get("leadership_rank"))
    if rank is not None:
        basis["rank"] = rank
    return basis


def _observed(basis: Mapping[str, Any]) -> dict[str, Any]:
    return {"state": "observed", "basis": dict(basis)}


def _unavailable(reason: str) -> dict[str, str]:
    return {"state": "unavailable", "reason": reason}
