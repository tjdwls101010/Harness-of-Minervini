"""Readable completed bars and shared evidence windows."""

from __future__ import annotations

import math
from datetime import date
from typing import Any
import numpy as np
import pandas as pd
from ..numbers import REPORTED_PRECISION as _REPORTED_PRECISION
from ..numbers import finite_or_none as _finite
from ..setup_structure import session_index
from .. import doctrine

from . import _BLOCKS


_ROLES = "management.ema21_sma50_roles"
_TWENTY_DAY = "management.close_below_20_day_average_lowers_probability"
_VOLUME_STATE = "setup.volume_state_convention"
_CLOSING_RANGE = "setup.closing_range_formula"
_SPLIT_COLUMN = SPLIT_COLUMN = "Stock Splits"
_DISCONTINUITY = "convention.unexplained_price_discontinuity"
# Where this convention's numbers are published inside a canonical block, they carry their
# own claim and their own non-binding stamp: the baseline length and the low/high ratios
# are TraderLion's, not Minervini's, and a reader must be able to see whose they are.
_VOLUME_CONVENTION = {"doctrine_id": _VOLUME_STATE, "binds": False, "source": "[TL]"}
AVERAGES = ("ema21", "sma50")


BLOCKS = _BLOCKS


def _unread_claim_inputs(claim_ids: tuple[str, ...], consumed: tuple[str, ...]) -> list[str]:
    """Which of the cited claims' required inputs this reading never consumes.

    Derived rather than written down beside each block, because a hand-kept list is the one
    thing that can disagree with the claim it is describing -- and a citation that reads as
    covering the whole claim while measuring half of it is exactly the contradiction this
    evidence pack exists to prevent. A block names what it opened; this names the rest.
    """

    required = {name for claim_id in claim_ids for name in doctrine.required_inputs(claim_id)}
    return sorted(required - set(consumed))


def _reported(value: float | None) -> float | None:
    return None if value is None else round(value, _REPORTED_PRECISION)


def _completed(frame: Any, as_of: date) -> pd.DataFrame | None:
    """The provider's bars, normalised the way the stop audit normalises them, through as_of."""

    if not isinstance(frame, pd.DataFrame) or frame.empty or not {"Close", "High", "Low"}.issubset(frame.columns):
        return None
    timestamps = pd.to_datetime(frame.index, errors="coerce")
    if timestamps.isna().any():
        return None
    timestamps = session_index(timestamps)
    ordered = frame.copy()
    ordered.index = timestamps
    ordered = ordered.sort_index()
    ordered = ordered[[timestamp.date() <= as_of for timestamp in ordered.index]]
    if ordered.empty:
        return None
    # A repeated session is one bar, and the last print of it is the one that completed.
    # Two prints of one session can carry different clock times, so the comparison is the
    # session date -- the same rule the stop audit applies to the same frame.
    ordered = ordered[~ordered.index.normalize().duplicated(keep="last")]
    for column in ("Open", "High", "Low", "Close", "Volume"):
        if column in ordered.columns:
            ordered[column] = pd.to_numeric(ordered[column], errors="coerce")
    return ordered


def _closing_range_pct(row: pd.Series) -> float | None:
    high, low, close = _finite(row["High"]), _finite(row["Low"]), _finite(row["Close"])
    if high is None or low is None or close is None or high <= low:
        return None
    return (close - low) / (high - low) * 100


def _closing_range(row: pd.Series) -> dict[str, Any]:
    """The closing range with the marker the source named beside it.

    The registry records the midpoint as a marker: a value named for comparison and never
    bounded, so what it produces is the measurement and its distance from that value. A
    bare percentage published under this claim would be a number citing a limit it never
    reported against.
    """

    measured = _closing_range_pct(row)
    return {
        "closing_range_pct": _reported(measured),
        "closing_range_marker": doctrine.evaluate_marker(_CLOSING_RANGE, "closing_range_midpoint_pct", measured),
        # Which of the session's own values the range could not be computed from. A null
        # beside no reason reads as a session with no range, which is not what happened.
        "closing_range_missing_inputs": [name for name, value in (("session_high", row["High"]), ("session_low", row["Low"]), ("session_close", row["Close"])) if _finite(value) is None],
    }


def _first_trouble(readable: _Readable, start: int) -> tuple[int | None, dict[str, Any] | None]:
    """The first session an average cannot be computed through, and how to say so.

    Two kinds of trouble bound an audit the same way. A split makes the closes on either
    side of it two coordinate systems; an unreadable close leaves the average nothing to be
    an average of from that session on. Neither reaches backwards -- the values before it
    were computed from readable closes in one coordinate system -- so both are a session
    the audit stops at rather than a reason to void the window and lose a declared exit
    that had already triggered.
    """

    split = readable.split_position(start)
    hole = readable.gap_position(start, columns=("Close",))
    if split is None and hole is None:
        return None, None
    if hole is None or (split is not None and split <= hole):
        return split, readable.split(start)
    return hole, readable.gap(start, columns=("Close",))


def _twenty_day_average(bars: pd.DataFrame, *, readable: _Readable) -> dict[str, Any]:
    length = int(doctrine.threshold(_TWENTY_DAY, "average_length_sessions"))
    gap = readable.gap(len(bars) - length, columns=("Close",)) or readable.split(len(bars) - length)
    if gap is not None:
        return {**gap, "doctrine_id": _TWENTY_DAY}
    closes = bars["Close"].astype(float)
    if len(closes) < length:
        return {"doctrine_id": _TWENTY_DAY, "state": "unavailable", "reason": "insufficient_history_for_average", "sessions_required": length}
    average = float(closes.rolling(length).mean().iloc[-1])
    close = _finite(closes.iloc[-1])
    if close is None or not math.isfinite(average) or average <= 0:
        return {"doctrine_id": _TWENTY_DAY, "state": "unavailable", "reason": "invalid_close"}
    return {
        "doctrine_id": _TWENTY_DAY,
        "claim_inputs_not_read": _unread_claim_inputs((_TWENTY_DAY,), ("price_history", "sma_20")),
        "state": "below" if close < average else "above",
        "date": bars.index[-1].date().isoformat(),
        "average": _reported(average),
        "close": _reported(close),
        "close_distance_pct": _reported((close - average) / average * 100),
    }


def _latest_tie(series: pd.Series, value: float) -> Any:
    """The index label of the last element that publishes as ``value``.

    Equality is asked of the reported figure rather than the raw binary one. Two declines
    that are the same decline can land on adjacent floats -- the same ratio reached by
    different multiplications -- and both print as the same percentage. Dating the finding
    at the earlier of them because their last bits differ is a tie the reader can see and
    the code could not.
    """

    reported = _reported(value)
    positions = [position for position, element in enumerate(series) if _reported(float(element)) == reported]
    return series.index[positions[-1]]


SMALLEST_RECOGNIZED_SPLIT_RATIO = float(doctrine.parameter(_DISCONTINUITY, "smallest_recognized_split_ratio"))


def split_sized_discontinuities(closes: Any) -> Any:
    """Which sessions moved too far from the session before them to be a move.

    A split is a discontinuity, so a history that omits its corporate actions still shows
    what one did: the close changes by the split ratio overnight. The harness cannot tell
    that from a fall the market actually made, and the two call for opposite answers -- one
    is arithmetic between two different shares, the other is a stop the tape took out. It
    refuses the window rather than guessing, at the ratio of the smallest ordinary split.
    """

    if closes is None:
        return None
    values = pd.to_numeric(closes, errors="coerce").to_numpy(dtype=float)
    if values.size < 2:
        return np.zeros(values.size, dtype=bool)
    previous, current = values[:-1], values[1:]
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = current / previous
    usable = np.isfinite(ratio) & (previous > 0) & (current > 0)
    jumped = usable & ((ratio >= SMALLEST_RECOGNIZED_SPLIT_RATIO) | (ratio <= 1.0 / SMALLEST_RECOGNIZED_SPLIT_RATIO))
    # Marked on the session that printed the new coordinate system, the way a split event
    # is stamped on the session it took effect.
    return np.concatenate(([False], jumped))


def impossible_bar_relations(bars: pd.DataFrame) -> Any:
    """Which sessions report a price outside the range that session claims to have had.

    A close under its own low, an open above its own high, a high beneath its own low --
    none of these is a session that happened, and no reading can decide which of the four
    numbers is the wrong one. The point is not tidiness. The audits read Lows and the
    current price is the Close, so a bar like this hands one reader a window that came
    through clear and the other a price far under the stop, and the verdict then contradicts
    the record printed beside it. So the whole bar is unusable, the way a NaN is.
    """

    columns = {name: pd.to_numeric(bars[name], errors="coerce").to_numpy(dtype=float) for name in ("Open", "High", "Low", "Close") if name in bars.columns}
    if "High" not in columns or "Low" not in columns:
        return None
    # Only prices that are prices take part. A zero or a NaN in one column is already that
    # column's own unreadable value, and letting it fail the relation test as well would
    # make one broken cell void the whole bar -- the opposite of the rule that a bad Volume
    # does not spoil a count of Opens. What is left is a genuine contradiction: four usable
    # numbers that cannot all be true of one session.
    usable = {name: (np.isfinite(value) & (value > 0)) for name, value in columns.items()}
    high, low = columns["High"], columns["Low"]
    broken = np.zeros(len(bars), dtype=bool)
    # A high beneath its own low needs no separate test: any close inside the frame is then
    # either above that high or below that low, so the containment test below catches it.
    for name in ("Open", "Close"):
        value = columns.get(name)
        if value is None:
            continue
        inside = usable[name]
        broken = broken | (inside & usable["High"] & (value > high)) | (inside & usable["Low"] & (value < low))
    return broken


class _Readable:
    """Which sessions the harness can read, asked one window at a time.

    A price of zero or NaN is not a cheap stock or a quiet session -- it is a bar the
    provider could not fill, and a measurement computed through it divides by nothing or
    silently compares false. But a bad bar only spoils the measurements that read it: a
    broken session from two years ago has nothing to do with the twenty-day average or
    with a position opened last week, and voiding those would hide evidence that is fine.
    So every block asks about its own lookback and no other.
    """

    def __init__(self, bars: pd.DataFrame) -> None:
        self._discontinuity_reason = "corporate_action_evidence_missing"
        self._bad: dict[str, Any] = {}
        for column, floor in (("Open", 0.0), ("High", 0.0), ("Low", 0.0), ("Close", 0.0), ("Volume", -1.0)):
            if column not in bars.columns:
                continue
            values = pd.to_numeric(bars[column], errors="coerce").to_numpy(dtype=float)
            self._bad[column] = ~np.isfinite(values) | (values <= floor)
        relations = impossible_bar_relations(bars)
        if relations is not None:
            for column in self._bad:
                self._bad[column] = self._bad[column] | relations
        self._length = len(bars)
        self._bars = bars
        if _SPLIT_COLUMN in bars.columns:
            events = pd.to_numeric(bars[_SPLIT_COLUMN], errors="coerce").to_numpy(dtype=float)
            # A blank event cell has not said there was no split. Left as NaN it fails both
            # comparisons below and so is uncrossable already; filling it with a zero would
            # turn missing evidence into an assertion of absence, and the session beside it
            # can carry a split-sized fall the window would then measure across. Which of
            # the two it was is kept separately, because they are refused under different
            # reasons -- a declared event, or evidence the provider never gave.
            self._splits = (events != 0) & (events != 1)
            self._unreadable_events = ~np.isfinite(events)
            self._split_reason = "share_split_inside_window"
        else:
            # A history without the event column has not said there was no split. What a
            # hidden split does to these measurements is print a discontinuity, so the
            # closes are asked for one directly and the window is refused the same way.
            self._splits = split_sized_discontinuities(bars.get("Close"))
            self._unreadable_events = None
            self._split_reason = self._discontinuity_reason

    def split(self, start: int = 0, end: int | None = None) -> dict[str, Any] | None:
        """The unavailable block for a window a share split falls inside, or None.

        The provider returns the prices the tape printed, unadjusted, with the split events
        beside them. Across a split those prices are two coordinate systems: the entry and
        the stop the trader declared are in the old one and the closes are in the new one,
        so an average, a percentage or a level comparison spanning the event is arithmetic
        between two different shares. The harness does not restate the trade, so it names
        the session it cannot measure across instead of selling on the arithmetic.
        """

        found = self.split_position(start, end)
        if found is None:
            return None
        blank = self._unreadable_events is not None and bool(self._unreadable_events[found])
        reason = self._discontinuity_reason if blank else self._split_reason
        return {"state": "unavailable", "reason": reason, "date": self._bars.index[found].date().isoformat()}

    def split_position(self, start: int = 0, end: int | None = None) -> int | None:
        """Where in the frame the window's first uncrossable session sits, or None.

        An audit that must refuse a window can still have read the sessions before the
        event honestly, so the position is published as well as the refusal.
        """

        if self._splits is None:
            return None
        # From the session after the window opens. The event is stamped on the session that
        # printed the new coordinate system, so a window starting there is entirely inside
        # that system and nothing in it spans the change. The stop audit reads the boundary
        # this way, and one frame must not be two different frames to two readers.
        first = max(0, start) + 1
        window = self._splits[first : self._length if end is None else end]
        if not bool(window.any()):
            return None
        return first + int(window.argmax())

    def gap(self, start: int = 0, end: int | None = None, columns: tuple[str, ...] = ("Open", "High", "Low", "Close", "Volume")) -> dict[str, Any] | None:
        """The unavailable block for a window holding a session this reading cannot use, or None.

        Columns as well as sessions: a broken Volume has nothing to do with an average of
        closes, and voiding one because of the other hides a measurement that is fine.
        """

        first = self.gap_position(start, end, columns)
        if first is None:
            return None
        return {"state": "unavailable", "reason": "invalid_ohlc_history", "date": self._bars.index[first].date().isoformat()}

    def gap_position(self, start: int = 0, end: int | None = None, columns: tuple[str, ...] = ("Open", "High", "Low", "Close", "Volume")) -> int | None:
        """Where in the frame the window's first unusable session sits, or None.

        A reading that must refuse a window still read the sessions before the hole, and a
        finding among them already happened. The position is what lets an audit stop there
        instead of throwing away what it had.
        """

        first: int | None = None
        for column in columns:
            mask = self._bad.get(column)
            if mask is None:
                continue
            window = mask[max(0, start) : self._length if end is None else end]
            if bool(window.any()):
                position = max(0, start) + int(window.argmax())
                first = position if first is None else min(first, position)
        return first

    def missing_at(self, positions: list[int], columns: tuple[str, ...]) -> dict[str, Any] | None:
        """The unavailable block for a reading that opens named cells rather than a span.

        Some readings are not a window at all: a return over twenty sessions opens two
        closes, and a volume ratio opens the sessions that fell. Guarding the span between
        them would refuse the reading over a bar it never touched.
        """

        found = [
            position
            for position in sorted(set(positions))
            if 0 <= position < self._length
            and any(self._bad.get(column) is not None and bool(self._bad[column][position]) for column in columns)
        ]
        if not found:
            return None
        return {"state": "unavailable", "reason": "invalid_ohlc_history", "date": self._bars.index[found[0]].date().isoformat()}

    def clean_positions(self, positions: list[int], columns: tuple[str, ...] = ("Close",)) -> list[int]:
        return [position for position in positions if all(not self._bad.get(column, np.zeros(self._length, dtype=bool))[position] for column in columns)]


def _positions_since(bars: pd.DataFrame, since: date) -> list[int]:
    return [position for position, timestamp in enumerate(bars.index) if timestamp.date() >= since]
