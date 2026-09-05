"""Malformed price histories shared by all four price consumers.

Whole-window measurements refuse every case here. Active stop audits deliberately retain
holes, duplicate sessions and range checks for their own window-specific evaluation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

AS_OF = "2025-12-31"
ENTRY = "2025-10-01"


def rising(sessions: int = 300) -> pd.DataFrame:
    """A history that qualifies on all eight criteria, so every rejection below is the only change."""

    index = pd.bdate_range(end=AS_OF, periods=sessions)
    close = pd.Series(np.linspace(50.0, 200.0, sessions), index=index, dtype=float)
    return pd.DataFrame(
        {"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close, "Volume": np.full(sessions, 1_000_000.0)},
        index=index,
    )


def doubled() -> pd.DataFrame:
    frame = rising()
    return pd.concat([frame, frame]).sort_index()


def intraday_pairs() -> pd.DataFrame:
    stamps = pd.DatetimeIndex([day + pd.Timedelta(hours=hour) for day in pd.bdate_range(end=AS_OF, periods=150) for hour in (10, 16)])
    close = pd.Series(np.linspace(50.0, 200.0, 300), index=stamps, dtype=float)
    return pd.DataFrame({"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close, "Volume": np.full(300, 1_000_000.0)}, index=stamps)


def holed() -> pd.DataFrame:
    frame = rising()
    frame.iloc[100:250, frame.columns.get_loc("Close")] = np.nan
    return frame


def negative_close() -> pd.DataFrame:
    frame = rising()
    frame.iloc[10, frame.columns.get_loc("Close")] = -5.0
    return frame


def inverted_bar() -> pd.DataFrame:
    frame = rising()
    frame.iloc[50, frame.columns.get_loc("High")] = 1.0
    return frame


def booleans() -> pd.DataFrame:
    frame = rising()
    frame["Close"] = True
    return frame


def complex_closes() -> pd.DataFrame:
    frame = rising()
    frame["Close"] = frame["Close"].astype(complex) + 1j
    return frame


def timestamps_as_prices() -> pd.DataFrame:
    frame = rising()
    frame["Close"] = pd.to_datetime("2020-01-01")
    return frame


def positional_index() -> pd.DataFrame:
    return rising().reset_index(drop=True)


def labelled_index() -> pd.DataFrame:
    frame = rising()
    frame.index = [str(position) for position in range(len(frame))]
    return frame


def repeated_column() -> pd.DataFrame:
    """A provider flattening a multi-level header prints one label twice."""

    frame = rising()
    return pd.concat([frame, frame["Close"]], axis=1)


def no_bars_at_all() -> pd.DataFrame:
    return rising().iloc[0:0]


def a_hole_in_the_closes() -> pd.DataFrame:
    frame = rising()
    frame.iloc[200, frame.columns.get_loc("Close")] = np.nan
    return frame


def boolean_lows() -> pd.DataFrame:
    frame = rising()
    frame["Low"] = frame["Low"].astype(object)
    frame.iloc[list(frame.index).index(pd.Timestamp(ENTRY)) + 10, frame.columns.get_loc("Low")] = True
    return frame


def complex_prices() -> pd.DataFrame:
    frame = rising()
    for column in ("Open", "High", "Low", "Close"):
        frame[column] = frame[column].astype(complex) + 1j
    return frame


def epoch_index() -> pd.DataFrame:
    frame = rising()
    frame.index = pd.Index([stamp.value for stamp in frame.index])
    return frame


def risk_timestamps_as_prices() -> pd.DataFrame:
    frame = rising()
    for column in ("Open", "High", "Low", "Close"):
        frame[column] = pd.to_datetime("2020-01-01")
    return frame


def an_infinite_close() -> pd.DataFrame:
    frame = rising()
    frame.iloc[-1, frame.columns.get_loc("Close")] = np.inf
    return frame


def market_complex_prices() -> pd.DataFrame:
    frame = rising()
    for column, imaginary in (("Open", 1j), ("High", 2j), ("Low", 3j), ("Close", 4j), ("Volume", 5j)):
        frame[column] = frame[column].astype(complex) + imaginary
    return frame


def market_booleans() -> pd.DataFrame:
    frame = rising()
    for column in frame.columns:
        frame[column] = True
    return frame


def one_session_printed_twice() -> pd.DataFrame:
    """The repeat carries a different clock time, so only the session date betrays it."""

    frame = rising(259)
    repeat = frame.iloc[[0]].copy()
    repeat.index = pd.DatetimeIndex([frame.index[0] + pd.Timedelta(hours=12)])
    return pd.concat([frame, repeat]).sort_index()


def inverted_first_bar() -> pd.DataFrame:
    frame = rising()
    frame.iloc[0, frame.columns.get_loc("High")] = 60.0
    frame.iloc[0, frame.columns.get_loc("Low")] = 70.0
    return frame


# Each entry is a history and the name the shared reader gives for refusing it. The names are
# asserted rather than only the refusal, because a surface that refuses everything for one
# reason tells a reader nothing about which of these they are holding.
CASES = {
    "doubled": (doubled, "history_repeats_a_session", None),
    "intraday_pairs": (intraday_pairs, "history_repeats_a_session", None),
    "holed": (holed, "history_contains_non_numeric_values", None),
    "negative_close": (negative_close, "history_contains_non_positive_values", "history_contains_non_positive_values"),
    "inverted_bar": (inverted_bar, "history_contains_invalid_bar_ranges", None),
    "booleans": (booleans, "history_contains_non_numeric_values", "history_contains_non_numeric_values"),
    "complex_closes": (complex_closes, "history_contains_non_numeric_values", "history_contains_non_numeric_values"),
    "timestamps_as_prices": (timestamps_as_prices, "history_contains_non_numeric_values", "history_contains_non_numeric_values"),
    "positional_index": (positional_index, "history_index_is_not_dates", "history_index_is_not_dates"),
    "labelled_index": (labelled_index, "history_index_is_not_dates", "history_index_is_not_dates"),
    "repeated_column": (repeated_column, "history_repeats_a_column", "history_repeats_a_column"),
    "no_bars_at_all": (no_bars_at_all, "history_has_no_completed_bars", "history_has_no_completed_bars"),
    "a_hole_in_the_closes": (a_hole_in_the_closes, "history_contains_non_numeric_values", None),
    "boolean_lows": (boolean_lows, "history_contains_non_numeric_values", "history_contains_non_numeric_values"),
    "complex_prices": (complex_prices, "history_contains_non_numeric_values", "history_contains_non_numeric_values"),
    "epoch_index": (epoch_index, "history_index_is_not_dates", "history_index_is_not_dates"),
    "risk_timestamps_as_prices": (risk_timestamps_as_prices, "history_contains_non_numeric_values", "history_contains_non_numeric_values"),
    "an_infinite_close": (an_infinite_close, "history_contains_non_numeric_values", "history_contains_non_numeric_values"),
    "market_complex_prices": (market_complex_prices, "history_contains_non_numeric_values", "history_contains_non_numeric_values"),
    "market_booleans": (market_booleans, "history_contains_non_numeric_values", "history_contains_non_numeric_values"),
    "one_session_printed_twice": (one_session_printed_twice, "history_repeats_a_session", None),
    "inverted_first_bar": (inverted_first_bar, "history_contains_invalid_bar_ranges", None),
}
