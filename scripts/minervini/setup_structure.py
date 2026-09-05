"""Turn a caller's swing dates into a base structure completed bars can contradict.

The setup engine used to take `--price-geometry pass`, an assertion with nothing behind
it. This takes coordinates instead. They are still the caller's reading of the chart --
the source says so, calling swing segmentation chart-assisted -- but every claim in a
chain of dates is falsifiable: the session exists, the order holds, and a bar named as a
swing high really is the highest bar in the span its neighbours bound. A misread chart
now comes back as a contradiction naming the date, where a misread flag came back READY.

The chain alternates high, low, high, ... and ends on a high, because that last high is
the structural pivot: the source's entry is price trading "above the high of the pause",
so a chain with no final pause has not described an entry at all.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
import hashlib
import numbers
import json
import math
from typing import Any

import numpy as np
import pandas as pd


_REQUIRED_COLUMNS = ("Open", "High", "Low", "Close", "Volume")
# Carried when the provider supplies it, and validated as an event rather than as a price: it is
# zero on every ordinary session and the ratio on the day a split happened, so the positivity rule
# the price columns live under would reject every history that has it. What reads it is the one
# thing the raw tape cannot say -- a corporate action moves every printed price without moving
# anyone's money, and a one-for-two reverse split prints exactly the hundred percent advance the
# Power Play criteria ask for.
#
# Absent from the fingerprint, which names the five columns every surface reads. That is a known
# gap rather than a decision: two inputs with the same OHLCV and different split events digest
# identically while one of them is measurable and the other is not, so a Power Play verdict needs
# a digest of its own before a chart approval can be bound to it.
_CORPORATE_ACTION_COLUMN = "Stock Splits"
# The other event that takes a printed price down without taking anyone's money with it. A split
# rescales; a distribution subtracts. Both leave a decline in the tape that the company paid for.
_DISTRIBUTION_COLUMN = "Dividends"
# Two bars can legitimately tie for a span's extreme, and the anchor's own value is the
# one the maximum was taken from, so this only absorbs float representation noise.
_EXTREME_TOLERANCE = 1e-12


def _unresolved(state: str, problems: list[str]) -> dict[str, Any]:
    return {"state": state, "anchors": [], "contractions": [], "base": None, "problems": problems}


def completed_bars(history: Any) -> pd.DataFrame | None:
    """Sort and coerce a price history once, so validation and measurement read one frame.

    Both halves used to normalise separately, which meant a frame given out of order or with
    numeric strings validated against one reading and was measured against another.
    """

    return read_bars(history)[0]


def session_index(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Keep session wall-clock labels; callers own sorting and duplicate-session policy."""

    return index.tz_localize(None) if index.tz is not None else index


def read_bars(history: Any) -> tuple[pd.DataFrame | None, str | None]:
    """The completed bars, or nothing and the reason there are none.

    Callers that only measure want the frame; a capability reporting unavailability wants to say
    which kind it was. Silently returning nothing turned a provider handing back the same session
    twice into "this history segments into no base", which points a reader at the wrong problem.
    """

    if not isinstance(history, pd.DataFrame) or any(column not in history for column in _REQUIRED_COLUMNS):
        return None, "history_missing_required_columns"
    # A repeated column name makes the selection below return two columns under one label, and
    # everything downstream then compares a frame with a scalar. A provider flattening a
    # multi-level header can produce exactly that, and it raised where the envelope should have
    # carried typed unavailability.
    if history.columns.has_duplicates:
        return None, "history_repeats_a_column"
    if history.empty:
        return None, "history_has_no_completed_bars"
    carried = _REQUIRED_COLUMNS + tuple(
        column
        for column in (_CORPORATE_ACTION_COLUMN, _DISTRIBUTION_COLUMN)
        if column in history
    )
    bars = history.loc[:, list(carried)].copy()
    # `to_numeric` launders anything it can cast, and several things it can cast are not prices:
    # a boolean becomes 1.0, a complex number loses its imaginary part, a datetime becomes epoch
    # nanoseconds. Each was accepted and measured, and the complex case fingerprinted identically
    # to a real history with the same real part -- a provenance collision, not a rounding one.
    # So the column has to already be real numbers, or strings of them, rather than merely
    # castable to them.
    if any(not _holds_real_numbers(bars[column]) for column in carried):
        return None, "history_contains_non_numeric_values"
    for column in carried:
        bars[column] = pd.to_numeric(bars[column], errors="coerce")
    if bars.isna().any().any() or not bool(np.isfinite(bars.to_numpy(dtype=float)).all()):
        return None, "history_contains_non_numeric_values"
    prices = [column for column in _REQUIRED_COLUMNS if column != "Volume"]
    # A halted session really does trade nothing, so zero volume is data rather than a fault. A
    # zero price is not: the chart boundary already refuses those, and the two have to agree or a
    # chart renders while the fingerprint it is supposed to be approved by comes back empty.
    events = [column for column in carried if column == _CORPORATE_ACTION_COLUMN]
    if (bars[prices] <= 0).any().any() or (bars["Volume"] < 0).any() or (events and (bars[events] < 0).any().any()):
        return None, "history_contains_non_positive_values"
    # The adjusted close is a corrected price rather than one the session traded at, so it is
    # held to being a positive real number and to nothing about the bar's range.
    inverted = bars["High"] < bars["Low"]
    outside = (bars["Open"] < bars["Low"]) | (bars["Open"] > bars["High"]) | (bars["Close"] < bars["Low"]) | (bars["Close"] > bars["High"])
    # The chart boundary refuses these already. Accepting them here would let a setup measure and
    # fingerprint bars no chart would render, which is the opposite of one digest across both.
    if bool(inverted.any()) or bool(outside.any()):
        return None, "history_contains_invalid_bar_ranges"
    # A positional index converts silently -- integers become nanoseconds since 1970 -- so a
    # frame that never carried dates would be measured against dates it never had. By value
    # again, and by what the value is rather than which Python class holds it: `np.int64` is not
    # an `int`, and an object Index of those read as dates just as quietly.
    if any(_is_a_number(label) for label in bars.index):
        return None, "history_index_is_not_dates"
    try:
        index = pd.DatetimeIndex(bars.index)
    except Exception:
        # An index that is not dates is a data problem like any other, and the digest raising on
        # it is an internal failure where the envelope should carry typed unavailability -- the
        # same shape closed for infinities, still open on this axis.
        return None, "history_index_is_not_dates"
    if index.isna().any():
        # A missing stamp is not a date either, and it compares against nothing without raising.
        return None, "history_index_is_not_dates"
    # Two rows under one label make a bar lookup return a Series, and reading a price off it
    # raises inside the detector -- an internal contract failure where the envelope should carry
    # typed unavailability.
    if index.has_duplicates:
        return None, "history_repeats_a_session"
    # The production provider returns the exchange's own tz-aware index while the fixtures
    # are naive, so a swing date parsed from a string matched one and missed the other.
    #
    # The wall clock is kept and the zone dropped, not converted. A session's date is the one the
    # exchange traded it on, and converting to UTC pushes a late-afternoon bar onto the next day.
    # The chart boundary already read it this way, so the two surfaces were normalising the same
    # bars differently -- one accepting what the other called a repeated session, and even where
    # both accepted, fingerprinting different dates.
    index = session_index(index)
    normalized = index.normalize()
    # Two intraday stamps on one date are not duplicates until the time is dropped, and dropping
    # it is what the rest of the engine reads. Checking only before normalising let that pair
    # through and folded the cause back into "this history segments into no base".
    if normalized.has_duplicates:
        return None, "history_repeats_a_session"
    bars.index = normalized
    return (bars if bars.index.is_monotonic_increasing else bars.sort_index()), None


def read_price_kinds(history: Any, *, columns: Sequence[str] = _REQUIRED_COLUMNS) -> tuple[pd.DataFrame | None, str | None]:
    """The rules about what a price is and what a session label is, and only those.

    `read_bars` refuses a history with a hole in it, because every measurement it feeds reads a
    whole window and a partial read would report a 52-week high the ticker never printed. The
    stop audit answers a narrower question and can do better: it names the bar it could not read
    and reports the prefix it had already cleared, which tells a holder more than refusing them a
    verdict does. So it keeps its holes.

    What it never had is the other half. A hole is a price that is absent; a boolean, a complex
    number, a timestamp and a string are prices that are *wrong*, and `float()` turns each of
    them into a number anyway -- 1.0, a real part, epoch nanoseconds. Those are fabricated, and
    the audit sold and held positions on them. The same is true of an index that never carried
    dates: `pd.to_datetime` reads a positional one as nanoseconds after 1970 and the window
    lands in a year the position did not exist in.

    Every reason here is one of `read_bars`'s own, and
    `tests/260828/unit/test_two_readers_one_vocabulary.py` holds the two to that: what this
    accepts, that one accepts or refuses for a rule this deliberately does not have.
    """

    if not isinstance(history, pd.DataFrame) or any(column not in history for column in columns):
        return None, "history_missing_required_columns"
    if history.columns.has_duplicates:
        return None, "history_repeats_a_column"
    if history.empty:
        return None, "history_has_no_completed_bars"
    # The whole frame travels, not a projection of it: this reader's callers go on to read
    # columns it was never asked to check -- the corporate-action column the stop window audits
    # is an event rather than a price and lives under the opposite rules.
    bars = history.copy()
    if any(not _holds_real_numbers(bars[column]) for column in columns):
        return None, "history_contains_non_numeric_values"
    for column in columns:
        bars[column] = pd.to_numeric(bars[column], errors="coerce")
    checked = bars.loc[:, list(columns)]
    present = checked.notna()
    values = checked.to_numpy(dtype=float)
    # A hole stays a hole; an infinity does not. It is not a price the session traded at, it
    # divides into nonsense wherever a ratio reads it, and it leaves the envelope unable to
    # serialise -- so a caller gets no answer at all rather than a wrong one.
    if not bool(np.isfinite(values[present.to_numpy()]).all()):
        return None, "history_contains_non_numeric_values"
    prices = [column for column in columns if column != "Volume"]
    if prices and bool((checked[prices][present[prices]] <= 0).any().any()):
        return None, "history_contains_non_positive_values"
    if "Volume" in columns and bool((checked["Volume"][present["Volume"]] < 0).any()):
        return None, "history_contains_non_positive_values"
    # The event columns are checked whether or not the caller named them: they are the one thing
    # here the raw tape cannot say, and a corporate action moves every printed price without
    # moving anyone's money. Only against laundering, though. A column of words cannot coerce,
    # so the split audit already notices it and withholds itself by name -- a finer answer than
    # refusing the history. `True` is the opposite case: it coerces to 1, 1 reads as "no split",
    # and a halving on the tape becomes a stop breach on a position nobody stopped out of.
    for column in (_CORPORATE_ACTION_COLUMN, _DISTRIBUTION_COLUMN):
        if column in bars and _launders_into_a_number(bars[column]):
            return None, "history_contains_non_numeric_values"
        if column in bars:
            carried = pd.to_numeric(bars[column], errors="coerce")
            reported = carried.notna()
            if bool((carried[reported] < 0).any()) or not bool(np.isfinite(carried[reported].to_numpy(dtype=float)).all()):
                return None, "history_contains_non_positive_values"
    if any(_is_a_number(label) for label in bars.index):
        return None, "history_index_is_not_dates"
    try:
        index = pd.DatetimeIndex(bars.index)
    except Exception:
        return None, "history_index_is_not_dates"
    if index.isna().any():
        return None, "history_index_is_not_dates"
    # The wall clock is kept and the zone dropped, exactly as `read_bars` does it, because a
    # session's date is the one the exchange traded it on. The stop audit converted to New York
    # instead, so a UTC-stamped history had every session renamed to the day before and a breach
    # was recorded against a session the rest of the harness says does not exist.
    index = session_index(index)
    # The clock time survives, where `read_bars` normalises it away. That reader refuses a
    # repeated session outright, so the time carries nothing for it; this one's callers resolve
    # a repeat by keeping the print that came later in the day, and dropping the time first
    # would hand that choice to row order instead.
    bars.index = index
    return (bars if bars.index.is_monotonic_increasing else bars.sort_index(kind="stable")), None


def _launders_into_a_number(column: pd.Series) -> bool:
    """Whether this column holds something `float()` turns into a number it never was.

    The three that do it silently: a boolean becomes 1.0, a complex number becomes its real
    part, a timestamp becomes epoch nanoseconds. A word does not -- it raises, and the reader
    downstream already reports that by name -- so this is narrower than "is not a number".
    """

    if pd.api.types.is_bool_dtype(column) or pd.api.types.is_complex_dtype(column) or pd.api.types.is_datetime64_any_dtype(column):
        return True
    if column.dtype != object:
        return False
    return any(isinstance(value, (bool, np.bool_, complex, np.complexfloating, pd.Timestamp, np.datetime64)) and not _is_a_number(value) for value in column)


def _is_a_number(value: Any) -> bool:
    """A real number, whichever library's scalar is holding it -- booleans excepted."""

    if isinstance(value, (bool, np.bool_)):
        return False
    return isinstance(value, numbers.Real)


def _holds_real_numbers(column: pd.Series) -> bool:
    """Whether every entry is a price, rather than something that can be cast into one."""

    if pd.api.types.is_float_dtype(column) or pd.api.types.is_integer_dtype(column):
        return True
    # Object and string columns are inspected entry by entry. A provider handing back numbers as
    # text is ordinary; one handing back booleans, complex numbers or timestamps is not, and the
    # dtype alone tells the two apart in neither case.
    if column.dtype != object and not pd.api.types.is_string_dtype(column):
        return False
    for value in column:
        if _is_a_number(value):
            continue
        # A hole, whichever sentinel the provider wrote it with. `nan` already passed here by
        # being a Real, so refusing `None` made the same absence two different findings: a
        # reader that keeps its holes lost a stop breach it had already established the moment
        # a later bar came back `None` rather than `nan`.
        if value is None or value is pd.NaT or value is pd.NA:
            continue
        if isinstance(value, str):
            try:
                float(value)
            except ValueError:
                return False
            continue
        return False
    return True


def bars_fingerprint(history: Any) -> str | None:
    """One digest of the completed bars, so three surfaces can name the same input.

    A chain proposed by `ticker.swings`, the chart a person approved it from, and the setup
    that re-cut it all run over bars the provider could have revised in between. Without this
    a declaration that used to match and now does not is indistinguishable from a rule change:
    same fingerprint means the rules moved, a different one means the data did.
    """
    bars = completed_bars(history)
    if bars is None:
        return None
    records = [
        {"date": stamp.date().isoformat(), **{column: float(row[column]) for column in _REQUIRED_COLUMNS}}
        for stamp, row in bars.iterrows()
    ]
    canonical = json.dumps(
        {"columns": _REQUIRED_COLUMNS, "bars": records}, separators=(",", ":"), sort_keys=True, allow_nan=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _session(bars: pd.DataFrame, value: Any) -> pd.Timestamp | None:
    try:
        stamp = pd.Timestamp(value).normalize()
    except (TypeError, ValueError):
        return None
    return stamp if stamp in bars.index else None


def _iso(stamp: pd.Timestamp) -> str:
    return stamp.date().isoformat() if isinstance(stamp.date(), date) else str(stamp)


def resolve_structure(history: Any, anchors: Sequence[Any]) -> dict[str, Any]:
    """Validate an alternating chain of swing dates against the completed bars.

    Returns ``resolved`` with the contractions and base the chain describes, ``contradicted``
    with the offending dates named, or ``unavailable`` when there is nothing to check.
    """
    declared = [value for value in (anchors or []) if str(value).strip()]
    if not declared:
        return _unresolved("unavailable", ["no swing chain was declared"])

    bars = completed_bars(history)
    if bars is None:
        return _unresolved("unavailable", ["completed daily OHLCV is missing or invalid"])

    problems: list[str] = []
    if len(declared) < 3 or len(declared) % 2 == 0:
        problems.append(
            "the swing chain must alternate high and low and end on a high, so it needs an odd count of at least three dates"
        )

    stamps: list[pd.Timestamp] = []
    for value in declared:
        stamp = _session(bars, value)
        if stamp is None:
            problems.append(f"{value} is not a completed session in the price history")
        else:
            stamps.append(stamp)
    if len(stamps) != len(declared):
        return _unresolved("contradicted", problems)

    for earlier, later in zip(stamps, stamps[1:]):
        if earlier >= later:
            problems.append(f"{_iso(later)} does not come after {_iso(earlier)}")
    if problems:
        return _unresolved("contradicted", problems)

    resolved: list[dict[str, Any]] = []
    for position, stamp in enumerate(stamps):
        kind = "high" if position % 2 == 0 else "low"
        left = stamps[position - 1] if position > 0 else stamp
        right = stamps[position + 1] if position + 1 < len(stamps) else stamp
        span = bars.loc[left:right]
        if kind == "high":
            price = float(bars.at[stamp, "High"])
            extreme = float(span["High"].max())
        else:
            price = float(bars.at[stamp, "Low"])
            extreme = float(span["Low"].min())
        if not math.isclose(price, extreme, rel_tol=_EXTREME_TOLERANCE):
            problems.append(
                f"{_iso(stamp)} is declared a swing {kind} but is not the {kind} of the span its neighbours bound"
            )
        resolved.append({"date": _iso(stamp), "kind": kind, "price": price})

    contractions: list[dict[str, Any]] = []
    for position in range(0, len(resolved) - 1, 2):
        high, low = resolved[position], resolved[position + 1]
        if high["price"] <= low["price"]:
            problems.append(f"the contraction beginning {high['date']} does not decline")
            continue
        contractions.append(
            {
                "high_date": high["date"],
                "high": high["price"],
                "low_date": low["date"],
                "low": low["price"],
                "depth_pct": (high["price"] - low["price"]) / high["price"] * 100,
                # The recovery ends where the next swing high stands, which is what makes
                # "volume on the final contraction" a window rather than a phrase.
                "recovery_end": resolved[position + 2]["date"],
            }
        )

    if problems:
        return _unresolved("contradicted", problems)

    base_high = resolved[0]["price"]
    base_low = min(item["low"] for item in contractions)
    start, end = stamps[0], stamps[-1]
    return {
        "state": "resolved",
        "anchors": resolved,
        "contractions": contractions,
        "base": {
            "start": _iso(start),
            "end": _iso(end),
            "high": base_high,
            "low": base_low,
            "depth_pct": (base_high - base_low) / base_high * 100,
            "duration_sessions": int(len(bars.loc[start:end])),
            # The last declared high is the pivot: the source's trigger is price trading
            # above the high of the final pause, not above a rolling window's maximum.
            "pivot": resolved[-1]["price"],
            "pivot_date": resolved[-1]["date"],
        },
        "problems": [],
    }


__all__ = ["bars_fingerprint", "completed_bars", "read_bars", "resolve_structure", "session_index"]
