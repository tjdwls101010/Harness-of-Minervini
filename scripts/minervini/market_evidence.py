"""Pure adapters for the evidence consumed by :mod:`scripts.minervini.market`.

The adapters deliberately preserve source observations.  They do not assign a
bullish or bearish breadth reading, infer leader behavior from RS rank, or make
a weighted group score.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from html.parser import HTMLParser
import math
import re
from typing import Any


_FINVIZ_SECTIONS = (
    ("advancing_declining", "advancing", "declining"),
    ("new_high_low", "new_high", "new_low"),
    ("sma50", "above", "below"),
    ("sma200", "above", "below"),
)
_GROUP_METRICS = ("price_momentum", "breadth", "high_proximity", "rs_concentration", "stage2_candidates", "leader_behavior")
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
) -> dict[str, Any]:
    """Convert completed source snapshots to ``evaluate_market_snapshot`` input.

    ``trade_traction`` intentionally has no default: it is user feedback, never
    an inference from market, Finviz, or RS data.
    """
    return {
        "breadth": _finviz_breadth(finviz_html),
        "qqq_21ema": _qqq_21ema_switch(qqq_daily_ohlcv),
        "sectors": _group_evidence(sector_rows, "sector"),
        "industries": _group_evidence(industry_rows, "industry"),
        "leaders": _leader_evidence(leader_rows),
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


def _group_evidence(rows: Iterable[Mapping[str, Any]] | None, group_type: str) -> list[dict[str, Any]] | None:
    if rows is None:
        return None
    if isinstance(rows, (str, bytes, Mapping)):
        return None
    result: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            continue
        basis = _basis(row)
        name = row.get("name") or row.get(group_type) or row.get("id") or f"{group_type}-{index + 1}"
        group = {
            "name": str(name),
            "basis": basis,
            "source_row": dict(row),
        }
        for metric in _GROUP_METRICS:
            explicit = row.get(metric)
            if explicit is not None:
                group[metric] = explicit
            elif metric == "rs_concentration" and basis:
                group[metric] = _observed(basis)
            elif metric == "leader_behavior" and row.get("leader_tickers"):
                group[metric] = _observed(basis)
            else:
                group[metric] = _unavailable("not_supplied_by_rs_source")
        result.append(group)
    return result


def _leader_evidence(rows: Iterable[Mapping[str, Any]] | None) -> list[dict[str, Any]] | None:
    if rows is None:
        return None
    if isinstance(rows, (str, bytes, Mapping)):
        return None
    leaders: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        basis = _basis(row)
        behavior = row.get("behavior", row.get("leader_behavior"))
        leaders.append(
            {
                "ticker": row.get("ticker"),
                "behavior": behavior if behavior is not None else _observed(basis),
                "basis": basis,
                "source_row": dict(row),
            }
        )
    return leaders


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
